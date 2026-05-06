import {
  EngineRuntimeInfo,
  suppressionEngineService,
} from './SuppressionEngineService';

export interface ModelPrepareResult {
  runtimeInfo: EngineRuntimeInfo;
  usedBundledModel: boolean;
  message?: string;
}

class ModelBundleService {
  async ensurePrepared(): Promise<ModelPrepareResult> {
    const runtimeInfo = await suppressionEngineService.prepare();
    return {
      runtimeInfo,
      usedBundledModel: true,
    };
  }
}

export const modelBundleService = new ModelBundleService();
