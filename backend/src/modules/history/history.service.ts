import { Inject, Injectable } from "@nestjs/common";
import { PrismaService } from "../../shared/prisma/prisma.service";
import { CreateHistoryDto } from "./dto/history.dto";

@Injectable()
export class HistoryService {
  constructor(@Inject(PrismaService) private readonly prisma: PrismaService) {}

  create(userId: string, dto: CreateHistoryDto) {
    return this.prisma.processingHistory.create({
      data: {
        userId,
        fileName: dto.file_name,
        durationSeconds: dto.duration_seconds,
        modelVersion: dto.model_version,
        platform: dto.platform,
        status: dto.status ?? "success",
        errorMessage: dto.error_message,
      },
    });
  }

  async list(userId: string, page: number, perPage: number) {
    const where = { userId };
    const [total, items] = await this.prisma.$transaction([
      this.prisma.processingHistory.count({ where }),
      this.prisma.processingHistory.findMany({
        where,
        orderBy: { createdAt: "desc" },
        skip: (page - 1) * perPage,
        take: perPage,
      }),
    ]);
    return { total, page, per_page: perPage, items: items.map((item) => ({
      id: item.id,
      file_name: item.fileName,
      duration_seconds: item.durationSeconds,
      model_version: item.modelVersion,
      platform: item.platform,
      status: item.status,
      created_at: item.createdAt,
    })) };
  }

  async clear(userId: string) {
    const result = await this.prisma.processingHistory.deleteMany({ where: { userId } });
    return result.count;
  }
}
