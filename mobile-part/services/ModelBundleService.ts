import { api } from './api';
import {
  EngineRuntimeInfo,
  suppressionEngineService,
} from './SuppressionEngineService';

export interface LatestAndroidModelResponse {
  has_update: boolean;
  current_version: string | null;
  latest_version: string;
  download_url: string | null;
  file_size_mb: number | null;
  checksum: string | null;
  bundle_kind: string | null;
  filename: string | null;
}

export interface ModelPrepareResult {
  runtimeInfo: EngineRuntimeInfo;
  usedBundledFallback: boolean;
  message?: string;
}

function resolveAbsoluteUrl(downloadUrl: string): string {
  const baseUrl = api.defaults.baseURL;
  if (!baseUrl) {
    throw new Error('API base URL is not configured');
  }

  if (downloadUrl.startsWith('http://') || downloadUrl.startsWith('https://')) {
    return downloadUrl;
  }

  return `${baseUrl.replace(/\/$/, '')}${downloadUrl}`;
}

class ModelBundleService {
  async ensurePrepared(accessToken: string): Promise<ModelPrepareResult> {
    const runtime = await suppressionEngineService.getRuntimeInfo().catch(() => null);
    const currentVersion = runtime?.modelVersion ?? undefined;

    try {
      const response = await api.get<LatestAndroidModelResponse>('/model/latest', {
        params: {
          platform: 'android',
          current_version: currentVersion,
        },
      });

      const latest = response.data;
      const runtimeInfo = await suppressionEngineService.prepare({
        bundleDownloadUrl:
          latest.has_update && latest.download_url
            ? resolveAbsoluteUrl(latest.download_url)
            : undefined,
        accessToken,
        expectedVersion: latest.latest_version,
        expectedChecksum: latest.checksum ?? undefined,
        forceRefresh: latest.has_update,
      });
      return {
        runtimeInfo,
        usedBundledFallback: false,
      };
    } catch (error) {
      console.warn('[ModelBundleService] Backend model update check failed; using bundled model.', error);
      const runtimeInfo = await suppressionEngineService.prepare({
        forceRefresh: false,
      });
      return {
        runtimeInfo,
        usedBundledFallback: true,
        message: 'Using bundled model; backend update check is unavailable.',
      };
    }
  }
}

export const modelBundleService = new ModelBundleService();
