import { IsNumber, IsOptional, IsString, Max, Min, MaxLength } from "class-validator";
import { Type } from "class-transformer";

export class CreateHistoryDto {
  @IsOptional()
  @IsString()
  @MaxLength(255)
  file_name?: string;

  @IsOptional()
  @IsNumber()
  duration_seconds?: number;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  model_version?: string;

  @IsOptional()
  @IsString()
  @MaxLength(50)
  platform?: string;

  @IsOptional()
  @IsString()
  @MaxLength(50)
  status?: string;

  @IsOptional()
  @IsString()
  @MaxLength(1000)
  error_message?: string;
}

export class HistoryQueryDto {
  @Type(() => Number)
  @Min(1)
  page = 1;

  @Type(() => Number)
  @Min(1)
  @Max(100)
  per_page = 20;
}
