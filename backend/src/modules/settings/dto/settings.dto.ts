import { IsObject } from "class-validator";

export class UpdateSettingsDto {
  @IsObject()
  data!: Record<string, unknown>;
}
