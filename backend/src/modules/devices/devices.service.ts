import { Inject, Injectable } from "@nestjs/common";
import { PrismaService } from "../../shared/prisma/prisma.service";
import { RegisterDeviceDto } from "./dto/device.dto";

@Injectable()
export class DevicesService {
  constructor(@Inject(PrismaService) private readonly prisma: PrismaService) {}

  async register(userId: string, dto: RegisterDeviceDto) {
    await this.prisma.userDevice.upsert({
      where: {
        userId_deviceId: {
          userId,
          deviceId: dto.device_id,
        },
      },
      create: {
        userId,
        deviceId: dto.device_id,
        platform: dto.platform,
        appVersion: dto.app_version,
      },
      update: {
        platform: dto.platform,
        appVersion: dto.app_version,
        lastSeenAt: new Date(),
      },
    });
  }
}
