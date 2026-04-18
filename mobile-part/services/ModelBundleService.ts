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
  async ensurePrepared(accessToken: string): Promise<EngineRuntimeInfo> {
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
      return suppressionEngineService.prepare({
        bundleDownloadUrl:
          latest.has_update && latest.download_url
            ? resolveAbsoluteUrl(latest.download_url)
            : undefined,
        accessToken,
        expectedVersion: latest.latest_version,
        expectedChecksum: latest.checksum ?? undefined,
        forceRefresh: latest.has_update,
      });
    } catch {
      return suppressionEngineService.prepare({
        forceRefresh: false,
      });
    }
  }
}

export const modelBundleService = new ModelBundleService();
