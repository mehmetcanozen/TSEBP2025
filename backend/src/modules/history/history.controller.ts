import { Body, Controller, Delete, Get, Inject, Post, Query, UseGuards } from "@nestjs/common";
import { User } from "@prisma/client";
import { BearerAuthGuard } from "../auth/bearer-auth.guard";
import { CurrentUser } from "../auth/current-user.decorator";
import { CreateHistoryDto, HistoryQueryDto } from "./dto/history.dto";
import { HistoryService } from "./history.service";

@Controller("api/v1/history")
@UseGuards(BearerAuthGuard)
export class HistoryController {
  constructor(@Inject(HistoryService) private readonly history: HistoryService) {}

  @Post()
  create(@CurrentUser() user: User, @Body() body: CreateHistoryDto) {
    return this.history.create(user.id, body);
  }

  @Get()
  list(@CurrentUser() user: User, @Query() query: HistoryQueryDto) {
    return this.history.list(user.id, query.page, query.per_page);
  }

  @Delete()
  async clear(@CurrentUser() user: User) {
    const count = await this.history.clear(user.id);
    return { message: `${count} history entries deleted.` };
  }
}
