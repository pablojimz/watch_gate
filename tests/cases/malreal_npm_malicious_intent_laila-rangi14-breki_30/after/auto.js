const fs = require('fs');
const { exec } = require('child_process');

let publishCount = 0;

const indonesianNames = ["andi", "budi", "cindy", "dewi", "erwin", "fitri", "gilang", "hendra", "irma", "joko", "kiki", "lina", "maya", "nina", "ocha", "patria", "qori", "rina", "sari", "tuti", "udin", "vina", "wati", "xaver", "yanti", "zain", "ade", "bayu", "citra", "dian", "eko", "fauzi", "gita", "hadi", "ida", "joni", "kurnia", "lisa", "maman", "nana", "ogi", "putri", "rudi", "sinta", "tomi", "umi", "vera", "wawan", "yuni", "zul", "agus", "bambang", "cici", "dono", "eka", "fajar", "galih", "hanafi", "indah", "joko", "kurniawan", "lutfi", "mulyono", "nurul", "okta", "putra", "riana", "siska", "tania", "utomo", "vida", "wibowo", "yanti", "zaki", "arif", "bella", "candra", "dewanto", "erick", "fadhil", "gita", "hadianto", "iwan", "jaja", "kresna", "laila", "mahesa", "nadia", "oktafian", "putri", "rifqi", "surya", "tiara"];

const indonesianFoods = ["rendang", "sate", "nasiuduk", "lontong", "bakso", "soto", "gudeg", "pecel", "gado-gado", "nasipecel", "tongseng", "rujak", "rawon", "nasicampur", "buburayam", "bubursumsum", "tahutek", "keraktelor", "serabi", "jengkol", "asinan", "nasi", "mie", "mieayam", "mieaceh", "miemee", "miebogor", "gorengan", "dodol", "klentik", "kupat", "mendoan", "gepuk", "rangginang", "kripik", "martabak", "nasisayur", "rujaksoto", "sroto", "jamblang", "brongkos", "semur", "telurtahu", "tempe", "sambel", "oncom", "tumis", "empal", "sambel", "telur", "gulai", "empal", "ikan", "bakwan", "botok", "brengkes", "donat", "esdoger", "kemplang", "kentang", "kue", "lapis", "mangut", "martabak", "naget", "oblok", "ongol-ongol", "otak-otak", "papeda", "pisang", "ragi", "rojak", "ronde", "sambalado", "sate", "semur", "soto", "tahu", "teh", "tempe", "toge", "tomat", "jus", "lodeh", "mangga", "kolak", "bika", "takokak", "tapai", "ketoprak", "sego", "liwet", "rangi", "lepet", "rangi", "sasag", "kembang", "gandul", "enting", "lutis", "tiwul", "ruwet", "saguer", "getuk", "mangut", "nasi", "lengko", "menjes", "bakwan", "ketan", "kue", "lapis", "taiwan", "kue", "lumpur", "kue", "kacang", "kue", "lupis", "kue", "moci", "kue", "mendut", "klanting", "keripik", "kepok", "klipo", "peyek", "gembus", "tahu", "tek", "wajit", "getas", "serimuka", "lapis", "dradag", "bubur", "gaplek", "kupang", "keripik", "ubi"];

function generateRandomName() {
  const randomName = indonesianNames[Math.floor(Math.random() * indonesianNames.length)];
  const randomFood = indonesianFoods[Math.floor(Math.random() * indonesianFoods.length)];
  const randomNumber = Math.floor(Math.random() * 100) + 1;

  return `${randomName}-${randomFood}${randomNumber}`;
}

function generateRandomDelay() {
  return 7000; // set delay to 7 seconds
}

function checkAndRemovePrivate() {
  const animation = ['Sedang memeriksa package...   ', 'Sedang memeriksa package.  ', 'Sedang memeriksa package.. ', 'Sedang memeriksa package...'];
  let currentFrame = 0;
  const animationInterval = setInterval(() => {
    process.stdout.write('\r' + animation[currentFrame]);
    currentFrame = (currentFrame + 1) % animation.length;
  }, 250);

  setTimeout(() => {
    clearInterval(animationInterval);
    process.stdout.write('\r');
    let packageJson = fs.readFileSync('package.json');
    let packageData = JSON.parse(packageJson);
    if (packageData.private === true) {
      console.log('Sedang mengubah package menjadi public...');
      delete packageData.private;
      fs.writeFileSync('package.json', JSON.stringify(packageData, null, 2));
      console.log('Package berhasil diubah menjadi public');
      const animationDelay = ['.', '..', '...', '....', '.....'];
      let currentFrame = 0;
      const animationInterval = setInterval(() => {
        process.stdout.write(animationDelay[currentFrame]);
        currentFrame = (currentFrame + 1) % animationDelay.length;
      }, 1000);
      setTimeout(() => {
        clearInterval(animationInterval);
        console.log('');
        checkAndRemovePrivate(); // Check again after 5 seconds animation
      }, 5000);
    } else {
      console.log('Tidak ada lagi private: true dalam package.json. Lanjut ke langkah berikutnya.');
      const animationDelay = ['.', '..', '...', '....', '.....'];
      let currentFrame = 0;
      const animationInterval = setInterval(() => {
        process.stdout.write(animationDelay[currentFrame]);
        currentFrame = (currentFrame + 1) % animationDelay.length;
      }, 1000);
      setTimeout(() => {
        clearInterval(animationInterval);
        console.log('');
        changePackageVersion();
      }, 5000);
    }
  }, 10000); // Wait for 10 seconds before starting
}

function changePackageVersion() {
  const animation = ['Sedang mengubah versi package...   ', 'Sedang mengubah versi package.  ', 'Sedang mengubah versi package.. ', 'Sedang mengubah versi package...'];
  let currentFrame = 0;
  const animationInterval = setInterval(() => {
    process.stdout.write('\r' + animation[currentFrame]);
    currentFrame = (currentFrame + 1) % animation.length;
  }, 250);

  setTimeout(() => {
    clearInterval(animationInterval);
    process.stdout.write('\r');
    let packageJson = fs.readFileSync('package.json');
    let packageData = JSON.parse(packageJson);
    const newVersion = `${Math.floor(Math.random() * 4) + 1}.${Math.floor(Math.random() * 4) + 1}.${Math.floor(Math.random() * 4) + 1}`;
    packageData.version = newVersion;
    fs.writeFileSync('package.json', JSON.stringify(packageData, null, 2));
    console.log(`Versi package telah diubah ke ${newVersion}`);
    publishWithDelay(); // Proceed to publish after changing version
  }, 10000); // Wait for 10 seconds before starting
}

function publishWithDelay() {
  const animation = ['Sabar lagi di proses   ', 'Sabar lagi di proses.  ', 'Sabar lagi di proses.. ', 'Sabar lagi di proses...'];
  let currentFrame = 0;
  const animationInterval = setInterval(() => {
    process.stdout.write('\r' + animation[currentFrame]);
    currentFrame = (currentFrame + 1) % animation.length;
  }, 250);

  let packageJson = fs.readFileSync('package.json');
  let packageData = JSON.parse(packageJson);
  let randomName = generateRandomName();
  packageData.name = `${randomName}-breki`; //ganti "-notthedevs" dengan apapun

  fs.writeFileSync('package.json', JSON.stringify(packageData, null, 2));

  let packageLockJson = fs.readFileSync('package-lock.json');
  let packageLockData = JSON.parse(packageLockJson);
  packageLockData.name = packageData.name;

  fs.writeFileSync('package-lock.json', JSON.stringify(packageLockData, null, 2));

  exec('npm publish --access public', (error, stdout, stderr) => {
    clearInterval(animationInterval);
    process.stdout.write('\r');
    if (error) {
      console.error(`Error: ${error}`);
      return;
    }
    if (stdout.includes("Sedang mem-publish harap tunggu") && stdout.includes("Sukses mem-publish!")) {
      publishCount++;
      console.log(`Sukses mem-publish! Total publish: ${publishCount}`);
    } else if (stdout.includes("429 Too Many Requests")) {
      console.error("Error: Limit publish! Coba lagi nanti.");
      return;
    }
    const delay = generateRandomDelay();
    console.log(`Publish selanjutnya ${delay / 1000} detik`);
    setTimeout(checkAndRemovePrivate, delay);
  });
}

// Start the process
checkAndRemovePrivate();
