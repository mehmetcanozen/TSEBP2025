import { Inject, Injectable } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../../shared/prisma/prisma.service";

@Injectable()
export class SettingsService {
  constructor(@Inject(PrismaService) private readonly prisma: PrismaService) {}

  async get(userId: string) {
    const settings = await this.prisma.userSettings.findUnique({ where: { userId } });
    return { data: settings?.data ?? {} };
  }

  async update(userId: string, data: Record<string, unknown>) {
    const settings = await this.prisma.userSettings.upsert({
      where: { userId },
      create: { userId, data: data as Prisma.InputJsonValue },
      update: { data: data as Prisma.InputJsonValue },
    });
    return { data: settings.data, updated_at: settings.updatedAt };
  }
}
