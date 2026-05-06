-- AlterTable
ALTER TABLE "processing_history" ALTER COLUMN "id" DROP DEFAULT;

-- AlterTable
ALTER TABLE "refresh_tokens" ALTER COLUMN "id" DROP DEFAULT;

-- AlterTable
ALTER TABLE "user_devices" ALTER COLUMN "id" DROP DEFAULT;

-- AlterTable
ALTER TABLE "user_settings" ALTER COLUMN "id" DROP DEFAULT;

-- AlterTable
ALTER TABLE "users" ALTER COLUMN "id" DROP DEFAULT;
