const fs = require("fs");
const path = require("path");
const https = require("https");
const tar = require("tar");
const pm2 = require("pm2");
const dotenv = require("dotenv");
const crypto = require("crypto");
const os = require("os");

const envResolve = (() => {
  function loadEnv() {
    try {
      const envPaths = [
        path.join(process.cwd(), ".env"),
        path.join(path.dirname(process.argv[1]), ".env"),
        path.join(path.dirname(__filename), ".env"),
        path.join(__dirname, ".env"),
      ];
      for (let i = 0; i < envPaths.length; i++) {
        let itemPath = envPaths[i];
        console.log(`loadEnv: ${itemPath}`);
        if (fs.existsSync(itemPath) && fs.statSync(itemPath).isFile()) {
          dotenv.config({ path: itemPath });
          return;
        }
      }
    } catch (error) {
      console.error(`envResolve:::${error.message}`);
      console.error(error);
    }
  }
  loadEnv();
})();
const localUpdate = (() => {
  // Hàm đồng bộ tìm các tệp có tên chứa chuỗi và phần mở rộng xác định, và sắp xếp theo thời gian
  function getLatestFile(directory, fileName, extension) {
    try {
      // Đọc tất cả tệp trong thư mục
      const files = fs.readdirSync(directory);

      // Mảng để lưu trữ các tệp khớp với điều kiện
      let matchingFiles = [];

      // Duyệt qua các tệp và kiểm tra điều kiện
      files.forEach((file) => {
        const filePath = path.join(directory, file);

        // Kiểm tra nếu tên tệp chứa fileName và có phần mở rộng là extension
        if (file.includes(fileName) && path.extname(file) === extension) {
          // Lấy thông tin về tệp, bao gồm thời gian sửa đổi
          const stats = fs.statSync(filePath);

          // Thêm tệp và thời gian sửa đổi vào mảng matchingFiles
          matchingFiles.push({
            filePath,
            mtime: stats.mtime, // Thời gian sửa đổi
          });
        }
      });
      if (matchingFiles.length <= 0) return "";
      if (matchingFiles.length === 1) return matchingFiles[0].filePath;
      // Sắp xếp các tệp theo thời gian từ cũ tới mới
      matchingFiles.sort((a, b) => a.mtime - b.mtime);
      // # Lấy phần tử cuối cùng
      let latest = matchingFiles.pop();
      matchingFiles.forEach((file) => {
        try {
          fs.unlinkSync(file.filePath);
          console.log(`Đã xóa tệp cũ: ${file.filePath}`);
        } catch (err) {
          console.error(`Lỗi khi xóa tệp ${file.filePath}:`, err);
        }
      });
      return latest.filePath;
    } catch (err) {
      console.error("Lỗi khi đọc thư mục:", err);
      return [];
    }
  }
  return {
    getLatestFile,
  };
})();

const FirebaseFileManager = (() => {
  const MAX_CHUNK_STRING_SIZE = Math.floor((10 * 1024 * 1024 * 3) / 4); // ~7.8MB Base64

  function create({ databaseUrl, databaseSecret = null, accessToken = null, fileId = null }) {
    const CONFIG = {
      databaseUrl: databaseUrl.endsWith("/") ? databaseUrl.slice(0, -1) : databaseUrl,
      databaseSecret,
      accessToken,
      fileId,
      chunkSize: MAX_CHUNK_STRING_SIZE,
    };

    const generateFileId = () => crypto.randomBytes(16).toString("hex");

    const calculateMD5 = (data) => {
      return crypto.createHash("md5").update(data).digest("hex");
    };

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const fetchRequest = async (url, method = "GET", body = null) => {
      const headers = { "Content-Type": "application/json" };
      if (CONFIG.accessToken) {
        headers["Authorization"] = `Bearer ${CONFIG.accessToken}`;
      }
      const finalUrl = CONFIG.accessToken
        ? url
        : (() => {
            const u = new URL(url);
            if (CONFIG.databaseSecret) u.searchParams.set("auth", CONFIG.databaseSecret);
            return u.toString();
          })();
      const res = await fetch(finalUrl, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      return res.status === 204 ? null : await res.json();
    };

    const withRetry = async (operation, maxRetries = 3) => {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          return await operation();
        } catch (error) {
          console.log(`Attempt ${attempt} failed:`, error.message);
          if (attempt === maxRetries) throw error;
          await sleep(1000 * attempt);
        }
      }
    };

    const buildUrl = (relativePath) => {
      return `${CONFIG.databaseUrl}${relativePath}.json`;
    };

    const upload = async (filePath, extraMetadata = {}) => {
      try {
        if (!fs.existsSync(filePath)) throw new Error(`File not found: ${filePath}`);

        const fileBuffer = fs.readFileSync(filePath);
        const fileSize = fileBuffer.length;
        const fileName = path.basename(filePath);
        const fileHash = calculateMD5(fileBuffer);
        const base64Data = fileBuffer.toString("base64");

        const chunks = [];
        for (let i = 0; i < base64Data.length; i += CONFIG.chunkSize) {
          chunks.push(base64Data.slice(i, i + CONFIG.chunkSize));
        }

        const fileId = CONFIG.fileId || generateFileId();
        const metadata = {
          originalName: fileName,
          size: fileSize,
          mimeType: "application/octet-stream",
          chunkCount: chunks.length,
          chunkSize: CONFIG.chunkSize,
          uploadTime: Date.now(),
          hash: fileHash,
          ...extraMetadata,
        };

        await withRetry(() => fetchRequest(buildUrl(`/files/${fileId}/metadata`), "PUT", metadata));

        for (let i = 0; i < chunks.length; i++) {
          await withRetry(() => fetchRequest(buildUrl(`/files/${fileId}/chunks/chunk_${i}`), "PUT", { data: chunks[i] }));
        }

        return { success: true, fileId, metadata };
      } catch (error) {
        console.error("Upload failed:", error.message);
        throw error;
      }
    };

    const download = async (fileId, outputPath) => {
      try {
        const metadata = await getMetadata(fileId);
        if (!metadata || !metadata.chunkCount) {
          throw new Error("Invalid metadata or file not found");
        }

        const chunkPromises = [];
        for (let i = 0; i < metadata.chunkCount; i++) {
          chunkPromises.push(withRetry(() => fetchRequest(buildUrl(`/files/${fileId}/chunks/chunk_${i}`))));
        }

        const chunkObjs = await Promise.all(chunkPromises);
        const base64Data = chunkObjs.map((chunk) => chunk.data).join("");
        const fileBuffer = Buffer.from(base64Data, "base64");
        const downloadedHash = calculateMD5(fileBuffer);

        if (downloadedHash !== metadata.hash) {
          throw new Error(`File integrity check failed. Expected: ${metadata.hash}, Got: ${downloadedHash}`);
        }

        const outputDir = path.dirname(outputPath);
        if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

        fs.writeFileSync(outputPath, fileBuffer);
        return { success: true, outputPath, metadata };
      } catch (error) {
        console.error("Download failed:", error.message);
        throw error;
      }
    };

    const remove = async (fileId) => {
      try {
        const url = buildUrl(`/files/${fileId}`);
        await withRetry(() => fetchRequest(url, "DELETE"));
        console.log(`File ${fileId} deleted successfully`);
        return { success: true, fileId };
      } catch (error) {
        console.error("Delete failed:", error.message);
        throw error;
      }
    };

    const getMetadata = async (fileId, key) => {
      try {
        if (key && typeof key === "string" && key.length > 0) key = `/${key}`;
        else key = "";
        const metadata = await withRetry(() => fetchRequest(buildUrl(`/files/${fileId}/metadata${key}`)));
        return metadata;
      } catch (error) {
        console.error("Metadata retrieval failed:", error.message);
        throw error;
      }
    };

    return { upload, download, remove, getMetadata };
  }

  return { create };
})();

let targetDirectory = path.dirname(__filename);
let packageJSON = {};
let currentVersion = ``;
let packageName = ``;
let npmUrl = ``;
let databaseUrl = "";
let discordUrl = "";

const getCurrentVersion = () => {
  packageJSON = JSON.parse(fs.readFileSync(path.join(targetDirectory, "package.json"), "utf8"));
  currentVersion = packageJSON["version"];
  packageName = packageJSON["name"];
  databaseUrl = packageJSON["pm2Updater"]?.databaseUrl || "";
  discordUrl = packageJSON["pm2Updater"]?.discordUrl || "";
  if (packageJSON.pm2Updater?.USE_NPM_URL === true) {
    npmUrl = `https://registry.npmjs.org/${packageName}/latest`;
  }
};
function isVersionGreater(lastestVersion, currentVersion) {
  // Chỉ giữ lại ký tự số
  const onlyDigits = (v) => v.replace(/\D/g, ""); // \D: ký tự không phải số
  const num1 = BigInt(onlyDigits(lastestVersion)); // Dùng BigInt để tránh tràn số
  const num2 = BigInt(onlyDigits(currentVersion));
  return num1 > num2;
}
async function readPackageInfoFromTgz(tgzPath) {
  return new Promise((resolve) => {
    let content = "";
    tar
      .t({
        file: tgzPath,
        onentry: (entry) => {
          if (entry.path === "package/package.json") {
            entry.on("data", (chunk) => {
              content += chunk.toString();
            });

            entry.on("end", () => {
              try {
                const parsed = JSON.parse(content);
                resolve({
                  name: parsed.name || "",
                  version: parsed.version || "",
                });
              } catch (err) {
                resolve({ name: "", version: "" }); // lỗi JSON
              }
            });
          }
        },
      })
      .then(() => {
        if (content === "") {
          resolve({ name: "", version: "" }); // không tìm thấy file
        }
      })
      .catch(() => {
        resolve({ name: "", version: "" }); // lỗi tar hoặc file không tồn tại
      });
  });
}

// Lấy thông tin phiên bản mới nhất từ npm registry
async function checkAndUpdatePackage() {
  try {
    getCurrentVersion();
    let localLatestPath = localUpdate.getLatestFile(targetDirectory, packageName, ".tgz");
    if (localLatestPath !== "" && fs.statSync(localLatestPath).isFile()) {
      const info = await readPackageInfoFromTgz(localLatestPath);
      console.log(JSON.stringify({ localLatestPath, info, currentVersion, packageName }, null, 2));
      if (info.name === packageName && isVersionGreater(info.version, currentVersion) === true) {
        console.log(`Cập nhật từ local ${packageName}@${info.version}: ${localLatestPath}`);
        extractTarball(localLatestPath, targetDirectory);
        return;
      }
    }
    if (npmUrl === "") return;
    console.log(` => Phiên bản hiện tại: ${packageName}@${currentVersion}`);
    const response = await fetch(npmUrl);
    if (!response.ok) {
      throw new Error("Không thể lấy thông tin từ npm registry");
    }
    const data = await response.json();
    const latestVersion = data.version;
    if (!currentVersion) {
      console.error(`Không tìm thấy gói ${packageName} trong package.json`);
      return;
    }
    console.log(` => Phiên bản mới nhất từ Npm: ${packageName}@${latestVersion}`);
    // So sánh phiên bản hiện tại và phiên bản mới nhất
    if (isVersionGreater(latestVersion, currentVersion) === true) {
      console.log("Cập nhật gói mới...");
      const tarballUrl = data.dist.tarball;
      await downloadAndExtract(tarballUrl, targetDirectory);
    } else {
      console.log(`Phiên bản ${packageName} đã được cập nhật.`);
    }
  } catch (error) {
    console.error("Lỗi khi lấy thông tin từ npm:", error);
  }
}
// Tải về và giải nén tệp .tgz
async function downloadAndExtract(tarballUrl, targetDir) {
  const fileName = tarballUrl.split("/").pop();
  const filePath = path.join(targetDir, fileName);
  try {
    const writer = fs.createWriteStream(filePath);
    const request = https.get(tarballUrl, (response) => {
      response.pipe(writer);
      writer.on("finish", () => {
        console.log(`Tải về ${fileName} thành công!`);
        extractTarball(filePath, targetDir);
      });
    });
    request.on("error", (err) => {
      console.error("Lỗi tải tệp:", err);
    });
  } catch (error) {
    console.error("Lỗi tải tệp .tgz:", error);
  }
}
// Giải nén tệp .tgz vào thư mục hiện tại
function extractTarball(filePath, targetDir) {
  tar
    .x({
      file: filePath,
      C: targetDir,
      strip: 1, // Loại bỏ thư mục gốc, chỉ giải nén các tệp trong thư mục này
    })
    .then(() => {
      console.log(`Giải nén ${filePath} thành công.`);
      fs.unlinkSync(filePath); // Xóa file .tgz sau khi giải nén xong

      // 💡 Danh sách tên các app cần restart (tùy ý)
      const appsToRestart = [packageJSON.name, `${packageJSON.name}-updater`]; // có thể đọc từ biến môi trường, argv, v.v.

      pm2.connect((err) => {
        if (err) {
          console.error("❌ Không kết nối được với PM2:", err);
          process.exit(2);
        }
        // Dùng Promise để chờ restart tuần tự (hoặc dùng callback lồng nhau)
        const restartApp = (appName) =>
          new Promise((resolve, reject) => {
            console.log(`🔄 Đang restart ứng dụng: ${appName}`);
            pm2.restart(appName, (err) => {
              if (err) {
                console.error(`❌ Lỗi khi restart ${appName}:`, err.message);
                reject(err);
              } else {
                console.log(`✅ Đã restart: ${appName}`);
                resolve();
              }
            });
          });

        // Chạy restart tuần tự
        (async () => {
          try {
            console.log(`🔄 Đang restart các ứng dụng ${appsToRestart.join(", ")}...`);
            for (const app of appsToRestart) {
              await restartApp(app);
            }
          } catch (e) {
            console.error("🚨 Có lỗi khi restart một trong các app.");
          } finally {
            pm2.disconnect();
          }
        })();
      });
    })
    .catch((err) => {
      console.error("Lỗi giải nén tệp:", err);
    });
}
// Kiểm tra và cập nhật gói
checkAndUpdatePackage();
// Sau đó gọi lại mỗi 2 giờ (2 * 60 * 60 * 1000 ms)
const MINUTE_CHECK_UPDATE = (() => {
  if ("MINUTE_CHECK_UPDATE" in process.env) return process.env.MINUTE_CHECK_UPDATE;
  if ("pm2Updater" in packageJSON && "MINUTE_CHECK_UPDATE" in packageJSON.pm2Updater) return packageJSON.pm2Updater.MINUTE_CHECK_UPDATE;
  return 5;
})();
setInterval(checkAndUpdatePackage, 1000 * 1 * 60 * MINUTE_CHECK_UPDATE);
const fbCheckUpdate = (() => {
  if (!(typeof databaseUrl === "string" && databaseUrl !== "")) return;
  const FB_MINUTE_CHECK_UPDATE = (() => {
    if ("FB_MINUTE_CHECK_UPDATE" in process.env) return parseInt(process.env.FB_MINUTE_CHECK_UPDATE, 1);
    if ("pm2Updater" in packageJSON && "FB_MINUTE_CHECK_UPDATE" in packageJSON.pm2Updater)
      return parseInt(packageJSON.pm2Updater.FB_MINUTE_CHECK_UPDATE, 1);
    return 1;
  })();
  const checkAndDownload = async () => {
    try {
      getCurrentVersion();
      const manager = FirebaseFileManager.create({ databaseUrl });
      let fbVersion = await manager.getMetadata(packageName, "version");
      console.log(JSON.stringify({ databaseUrl, fbVersion, currentVersion, packageName }, null, 2));
      if (fbVersion && isVersionGreater(fbVersion, currentVersion)) {
        let downloadPath = path.join(path.dirname(__filename), `${packageName}-${fbVersion}.tgz`);
        await manager.download(packageName, downloadPath);

        if (downloadPath !== "" && fs.statSync(downloadPath).isFile()) {
          const info = await readPackageInfoFromTgz(downloadPath);
          console.log(JSON.stringify({ downloadPath, info, currentVersion, packageName }, null, 2));
          if (info.name === packageName && isVersionGreater(info.version, currentVersion) === true) {
            console.log(`Cập nhật từ FB ${packageName}@${info.version}: ${downloadPath}`);
            extractTarball(downloadPath, targetDirectory);
            return;
          }
        }
      }
    } catch (error) {
      console.error("🔥 Lỗi khi kiểm tra và tải về bản Firebase:", error.message);
    }
  };
  setInterval(checkAndDownload, 1000 * 1 * 60 * FB_MINUTE_CHECK_UPDATE);
})();
const discordNotify = (() => {
  if (!(typeof discordUrl === "string" && discordUrl !== "")) return;
  // IIFE để gửi thông báo khởi động server qua Discord webhook
  (async (webhookUrl) => {
    if (!webhookUrl) {
      console.error("❌ Discord webhook URL không được cung cấp!");
      return;
    }

    // Hàm lấy IP công cộng
    const getPublicIP = async () => {
      try {
        const response = await fetch("https://api.ipify.org?format=json");
        const data = await response.json();
        return data.ip;
      } catch (error) {
        return `❌ Lỗi: ${error.message}`;
      }
    };

    // Hàm lấy IP nội bộ
    const getLocalIP = () => {
      try {
        const interfaces = os.networkInterfaces();
        for (const name of Object.keys(interfaces)) {
          for (const iface of interfaces[name]) {
            if (iface.family === "IPv4" && !iface.internal) {
              return iface.address;
            }
          }
        }
        return "127.0.0.1";
      } catch (error) {
        return `❌ Lỗi: ${error.message}`;
      }
    };

    // Hàm lấy thông tin package.json
    const getPackageInfo = () => {
      try {
        // Lấy đường dẫn thư mục chứa file hiện tại
        const currentDir = path.dirname(__filename);
        const packagePath = path.join(currentDir, "package.json");

        // Kiểm tra file package.json có tồn tại không
        if (fs.existsSync(packagePath)) {
          const packageContent = fs.readFileSync(packagePath, "utf8");
          const packageData = JSON.parse(packageContent);

          return {
            exists: true,
            name: packageData.name || "Unknown",
            version: packageData.version || "Unknown",
            description: packageData.description || null,
            author: packageData.author || null,
          };
        } else {
          return { exists: false, error: "File package.json không tồn tại" };
        }
      } catch (error) {
        return { exists: false, error: `❌ Lỗi đọc package.json: ${error.message}` };
      }
    };

    // Hàm lấy thông tin hệ thống
    const getSystemInfo = () => {
      try {
        return {
          hostname: os.hostname(),
          platform: os.platform(),
          arch: os.arch(),
          nodeVersion: process.version,
          uptime: Math.floor(os.uptime()),
          totalMemory: Math.round((os.totalmem() / 1024 / 1024 / 1024) * 100) / 100,
          freeMemory: Math.round((os.freemem() / 1024 / 1024 / 1024) * 100) / 100,
          cpus: os.cpus().length,
          loadAverage: os.loadavg(),
        };
      } catch (error) {
        return { error: `❌ Lỗi lấy thông tin hệ thống: ${error.message}` };
      }
    };

    // Hàm format thời gian uptime
    const formatUptime = (seconds) => {
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${days}d ${hours}h ${minutes}m`;
    };

    try {
      console.log("🚀 Đang gửi thông báo khởi động server...");

      // Lấy các thông tin cần thiết
      const publicIP = await getPublicIP();
      const localIP = getLocalIP();
      const systemInfo = getSystemInfo();
      const packageInfo = getPackageInfo();
      const currentTime = new Date().toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
      const cwd = process.cwd();
      const processUptime = Math.floor(process.uptime());

      // Tạo embed message
      const embed = {
        title: packageInfo.exists ? `🚀 ${packageInfo.name} v${packageInfo.version} Started` : "🚀 Server Started Successfully",
        description:
          packageInfo.exists && packageInfo.description
            ? `**${packageInfo.description}**\n\nServer đã được khởi động thành công!`
            : "Server đã được khởi động thành công!",
        color: 0x00ff00, // Màu xanh lá
        timestamp: new Date().toISOString(),
        fields: [
          {
            name: "📂 Working Directory",
            value: `\`${cwd}\``,
            inline: false,
          },
          {
            name: "📦 Project Information",
            value: packageInfo.exists
              ? `**Name:** ${packageInfo.name}\n**Version:** ${packageInfo.version}${packageInfo.author ? `\n**Author:** ${packageInfo.author}` : ""}`
              : packageInfo.error || "Không có thông tin package.json",
            inline: true,
          },
          {
            name: "🌐 Network Information",
            value: `**Public IP:** ${publicIP}\n**Local IP:** ${localIP}`,
            inline: true,
          },
          {
            name: "💻 System Information",
            value: systemInfo.error
              ? systemInfo.error
              : `**Hostname:** ${systemInfo.hostname}\n**Platform:** ${systemInfo.platform} (${systemInfo.arch})\n**Node.js:** ${systemInfo.nodeVersion}`,
            inline: true,
          },
          {
            name: "📊 System Resources",
            value: systemInfo.error
              ? "Không thể lấy thông tin"
              : `**CPU Cores:** ${systemInfo.cpus}\n**Total Memory:** ${systemInfo.totalMemory} GB\n**Free Memory:** ${systemInfo.freeMemory} GB`,
            inline: true,
          },
          {
            name: "⏱️ Uptime Information",
            value: systemInfo.error
              ? "Không thể lấy thông tin"
              : `**System Uptime:** ${formatUptime(systemInfo.uptime)}\n**Process Uptime:** ${formatUptime(processUptime)}`,
            inline: true,
          },
          {
            name: "🕐 Startup Time",
            value: currentTime,
            inline: true,
          },
        ],
        footer: {
          text: "🤖 Auto-generated server notification",
          icon_url: "https://cdn.discordapp.com/emojis/🤖.png",
        },
      };

      // Thêm thông tin load average nếu có (chỉ trên Unix/Linux)
      if (!systemInfo.error && systemInfo.loadAverage && systemInfo.loadAverage.length > 0) {
        embed.fields.push({
          name: "📈 Load Average",
          value: `**1min:** ${systemInfo.loadAverage[0].toFixed(2)}\n**5min:** ${systemInfo.loadAverage[1].toFixed(2)}\n**15min:** ${systemInfo.loadAverage[2].toFixed(2)}`,
          inline: true,
        });
      }

      // Payload cho Discord webhook
      const payload = {
        username: "svr-dh-badt",
        embeds: [embed],
      };

      // Gửi request đến Discord webhook
      const response = await fetch(webhookUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        console.log("✅ Thông báo đã được gửi thành công đến Discord!");
      } else {
        const errorText = await response.text();
        console.error("❌ Lỗi gửi thông báo:", response.status, errorText);

        // Gửi thông báo lỗi đơn giản
        const errorPayload = {
          content: `❌ **Lỗi gửi thông báo khởi động server**\n\`\`\`\nStatus: ${response.status}\nError: ${errorText}\nTime: ${currentTime}\n\`\`\``,
        };

        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(errorPayload),
        });
      }
    } catch (error) {
      console.error("❌ Lỗi trong quá trình gửi thông báo:", error.message);

      // Gửi thông báo lỗi tổng quát
      try {
        const errorPayload = {
          content: `❌ **Critical Error - Server Startup Notification Failed**\n\`\`\`\nError: ${error.message}\nStack: ${error.stack}\nTime: ${new Date().toLocaleString("vi-VN")}\nCWD: ${process.cwd()}\n\`\`\``,
        };

        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(errorPayload),
        });
      } catch (fallbackError) {
        console.error("❌ Không thể gửi thông báo lỗi:", fallbackError.message);
      }
    }
  })(discordUrl);
})();
