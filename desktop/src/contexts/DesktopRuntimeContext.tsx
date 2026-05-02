import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  browseForAudioInput,
  browseForOutputWav,
  cancelOfflineJob,
  deleteSpeakerProfile as deleteSpeakerProfileApi,
  getHive15Presets,
  getModelCategories,
  getRuntimeMetrics,
  getTargetSpeakerRuntimeInfo,
  getVirtualMicStatus,
  listSpeakerProfiles,
  listAudioDevices,
  saveSpeakerProfile as saveSpeakerProfileApi,
  startLiveMonitor,
  startOfflineJob,
  startTargetSpeakerJob,
  stopLiveMonitor,
  type AudioDevice,
  type Hive15Preset,
  type LiveMeterEvent,
  type LiveStatusEvent,
  type ModelCategory,
  type OfflineProgressEvent,
  type RuntimeMetrics,
  type SpeakerProfile,
  type TargetSpeakerEngine,
  type TargetSpeakerOutputMode,
  type TargetSpeakerRuntimeInfo,
  type VirtualMicStatus,
} from "@/lib/desktop-api";

type LiveOutputMode = "monitor" | "virtualMic";
type DesktopMode = "semanticSuppression" | "speakerSuppression";

interface DesktopRuntimeContextValue {
  categories: ModelCategory[];
  presets: Hive15Preset[];
  devices: AudioDevice[];
  runtimeMetrics: RuntimeMetrics | null;
  targetSpeakerInfo: TargetSpeakerRuntimeInfo | null;
  speakerProfiles: SpeakerProfile[];
  virtualMicStatus: VirtualMicStatus | null;
  desktopMode: DesktopMode;
  selectedCategories: string[];
  aggressiveness: number;
  speakerInputPath: string;
  speakerReferencePath: string;
  speakerOutputPath: string;
  speakerEngine: TargetSpeakerEngine;
  speakerOutputMode: TargetSpeakerOutputMode;
  speakerRemovalScale: number;
  selectedSpeakerProfileId: string;
  speakerProfileName: string;
  lookaheadMs: number;
  outputMode: LiveOutputMode;
  inputDeviceId: string;
  outputDeviceId: string;
  inputPath: string;
  outputPath: string;
  debugInputEnabled: boolean;
  debugInputPath: string;
  recordEnabled: boolean;
  recordOutputPath: string;
  liveStatus: LiveStatusEvent | null;
  liveMeter: LiveMeterEvent | null;
  offlineProgress: OfflineProgressEvent | null;
  activeLiveSessionId: string | null;
  activeOfflineJobId: string | null;
  isLoading: boolean;
  isStartingLive: boolean;
  isOfflineRunning: boolean;
  error: string | null;
  setDesktopMode: (value: DesktopMode) => void;
  setSelectedCategories: (categories: string[]) => void;
  toggleCategory: (categoryId: string) => void;
  applyPreset: (presetId: string) => void;
  setAggressiveness: (value: number) => void;
  setSpeakerInputPath: (value: string) => void;
  setSpeakerReferencePath: (value: string) => void;
  setSpeakerOutputPath: (value: string) => void;
  setSpeakerEngine: (value: TargetSpeakerEngine) => void;
  setSpeakerOutputMode: (value: TargetSpeakerOutputMode) => void;
  setSpeakerRemovalScale: (value: number) => void;
  setSelectedSpeakerProfileId: (value: string) => void;
  setSpeakerProfileName: (value: string) => void;
  setLookaheadMs: (value: number) => void;
  setOutputMode: (value: LiveOutputMode) => void;
  setInputDeviceId: (value: string) => void;
  setOutputDeviceId: (value: string) => void;
  setInputPath: (value: string) => void;
  setOutputPath: (value: string) => void;
  setDebugInputEnabled: (value: boolean) => void;
  setDebugInputPath: (value: string) => void;
  setRecordEnabled: (value: boolean) => void;
  setRecordOutputPath: (value: string) => void;
  browseInputPath: () => Promise<void>;
  browseOutputPath: () => Promise<void>;
  browseSpeakerInputPath: () => Promise<void>;
  browseSpeakerReferencePath: () => Promise<void>;
  browseSpeakerOutputPath: () => Promise<void>;
  browseDebugInputPath: () => Promise<void>;
  browseRecordOutputPath: () => Promise<void>;
  refreshDevices: () => Promise<void>;
  refreshVirtualMicStatus: () => Promise<void>;
  refreshRuntimeMetrics: () => Promise<void>;
  refreshTargetSpeakerInfo: () => Promise<void>;
  refreshSpeakerProfiles: () => Promise<void>;
  startOffline: () => Promise<void>;
  startSpeakerSuppression: () => Promise<void>;
  saveCurrentSpeakerProfile: () => Promise<void>;
  deleteSelectedSpeakerProfile: () => Promise<void>;
  cancelOffline: () => Promise<void>;
  startLive: () => Promise<void>;
  stopLive: () => Promise<void>;
  clearError: () => void;
}

const DesktopRuntimeContext = createContext<DesktopRuntimeContextValue | undefined>(undefined);

const INITIAL_LIVE_STATUS: LiveStatusEvent = {
  sessionId: "idle",
  state: "stopped",
  xruns: 0,
  provider: "idle",
  outputMode: "monitor",
  lookaheadMs: 150,
  estimatedLatencyMs: 0,
  realtimeHealth: "idle",
};

export const DesktopRuntimeProvider = ({ children }: { children: ReactNode }) => {
  const [categories, setCategories] = useState<ModelCategory[]>([]);
  const [presets, setPresets] = useState<Hive15Preset[]>([]);
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [runtimeMetrics, setRuntimeMetrics] = useState<RuntimeMetrics | null>(null);
  const [targetSpeakerInfo, setTargetSpeakerInfo] = useState<TargetSpeakerRuntimeInfo | null>(null);
  const [speakerProfiles, setSpeakerProfiles] = useState<SpeakerProfile[]>([]);
  const [virtualMicStatus, setVirtualMicStatus] = useState<VirtualMicStatus | null>(null);
  const [desktopMode, setDesktopMode] = useState<DesktopMode>("semanticSuppression");
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [aggressiveness, setAggressiveness] = useState(1.5);
  const [speakerInputPath, setSpeakerInputPath] = useState("");
  const [speakerReferencePath, setSpeakerReferencePath] = useState("");
  const [speakerOutputPath, setSpeakerOutputPath] = useState("");
  const [speakerEngine, setSpeakerEngine] = useState<TargetSpeakerEngine>("tsextract_onnx");
  const [speakerOutputMode, setSpeakerOutputMode] = useState<TargetSpeakerOutputMode>("remove_target");
  const [speakerRemovalScale, setSpeakerRemovalScale] = useState(1.0);
  const [selectedSpeakerProfileId, setSelectedSpeakerProfileIdState] = useState("");
  const [speakerProfileName, setSpeakerProfileName] = useState("");
  const [lookaheadMs, setLookaheadMs] = useState(150);
  const [outputMode, setOutputModeState] = useState<LiveOutputMode>("monitor");
  const [inputDeviceId, setInputDeviceId] = useState("");
  const [outputDeviceId, setOutputDeviceId] = useState("");
  const [inputPath, setInputPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [debugInputEnabled, setDebugInputEnabled] = useState(false);
  const [debugInputPath, setDebugInputPath] = useState("");
  const [recordEnabled, setRecordEnabled] = useState(false);
  const [recordOutputPath, setRecordOutputPath] = useState("");
  const [liveStatus, setLiveStatus] = useState<LiveStatusEvent | null>(INITIAL_LIVE_STATUS);
  const [liveMeter, setLiveMeter] = useState<LiveMeterEvent | null>(null);
  const [offlineProgress, setOfflineProgress] = useState<OfflineProgressEvent | null>(null);
  const [activeLiveSessionId, setActiveLiveSessionId] = useState<string | null>(null);
  const [activeOfflineJobId, setActiveOfflineJobId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStartingLive, setIsStartingLive] = useState(false);
  const [isOfflineRunning, setIsOfflineRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hydratedDefaults = useRef(false);

  const refreshDevices = async () => {
    try {
      const [loadedDevices, loadedVirtualMicStatus] = await Promise.all([
        listAudioDevices(),
        getVirtualMicStatus(),
      ]);
      setDevices(loadedDevices);
      setVirtualMicStatus(loadedVirtualMicStatus);

      const defaultInput = loadedDevices.find((device) => device.direction === "input" && device.default);
      const defaultOutput = loadedDevices.find((device) => device.direction === "output" && device.default);
      const firstInput = loadedDevices.find((device) => device.direction === "input");
      const firstOutput = loadedDevices.find((device) => device.direction === "output");

      setInputDeviceId((current) => current || defaultInput?.id || firstInput?.id || "");
      setOutputDeviceId((current) => current || defaultOutput?.id || firstOutput?.id || "");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to enumerate audio devices.");
    }
  };

  const refreshVirtualMicStatus = async () => {
    try {
      const status = await getVirtualMicStatus();
      setVirtualMicStatus(status);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to check virtual microphone status.");
    }
  };

  const refreshRuntimeMetrics = async () => {
    try {
      const metrics = await getRuntimeMetrics();
      setRuntimeMetrics(metrics);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to fetch runtime metrics.");
    }
  };

  const refreshTargetSpeakerInfo = async () => {
    try {
      const info = await getTargetSpeakerRuntimeInfo();
      setTargetSpeakerInfo(info);
      setSpeakerEngine((current) => (info.availableEngines.includes(current) ? current : info.defaultEngine));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to fetch target speaker runtime info.");
    }
  };

  const refreshSpeakerProfiles = async () => {
    try {
      const profiles = await listSpeakerProfiles();
      setSpeakerProfiles(profiles);
      setSelectedSpeakerProfileIdState((current) =>
        profiles.some((profile) => profile.id === current) ? current : "",
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load speaker profiles.");
    }
  };

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [
          loadedCategories,
          loadedPresets,
          loadedDevices,
          metrics,
          loadedTargetSpeakerInfo,
          loadedSpeakerProfiles,
          loadedVirtualMicStatus,
        ] = await Promise.all([
          getModelCategories(),
          getHive15Presets(),
          listAudioDevices(),
          getRuntimeMetrics(),
          getTargetSpeakerRuntimeInfo(),
          listSpeakerProfiles(),
          getVirtualMicStatus(),
        ]);

        if (cancelled) {
          return;
        }

        setCategories(loadedCategories);
        setPresets(loadedPresets);
        setDevices(loadedDevices);
        setRuntimeMetrics(metrics);
        setTargetSpeakerInfo(loadedTargetSpeakerInfo);
        setSpeakerProfiles(loadedSpeakerProfiles);
        setSpeakerEngine((current) =>
          loadedTargetSpeakerInfo.availableEngines.includes(current) ? current : loadedTargetSpeakerInfo.defaultEngine,
        );
        setVirtualMicStatus(loadedVirtualMicStatus);

        const defaultInput = loadedDevices.find((device) => device.direction === "input" && device.default);
        const defaultOutput = loadedDevices.find((device) => device.direction === "output" && device.default);
        const firstInput = loadedDevices.find((device) => device.direction === "input");
        const firstOutput = loadedDevices.find((device) => device.direction === "output");

        setInputDeviceId(defaultInput?.id || firstInput?.id || "");
        setOutputDeviceId(defaultOutput?.id || firstOutput?.id || "");

        if (!hydratedDefaults.current) {
          const defaultPreset = loadedPresets[0];
          if (defaultPreset) {
            setSelectedCategories(defaultPreset.categories);
          } else {
            setSelectedCategories(loadedCategories.slice(0, 3).map((category) => category.id));
          }
          hydratedDefaults.current = true;
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to initialize the desktop runtime.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const toggleCategory = (categoryId: string) => {
    setSelectedCategories((current) =>
      current.includes(categoryId)
        ? current.filter((value) => value !== categoryId)
        : [...current, categoryId],
    );
  };

  const applyPreset = (presetId: string) => {
    const preset = presets.find((value) => value.id === presetId);
    if (!preset) {
      return;
    }

    setSelectedCategories(preset.categories);
  };

  const updateSpeakerReferencePath = (value: string) => {
    setSpeakerReferencePath(value);
    setSelectedSpeakerProfileIdState((current) => {
      if (!current) {
        return current;
      }
      const profile = speakerProfiles.find((item) => item.id === current);
      return profile?.referencePath === value ? current : "";
    });
  };

  const setSelectedSpeakerProfileId = (profileId: string) => {
    setSelectedSpeakerProfileIdState(profileId);
    const profile = speakerProfiles.find((item) => item.id === profileId);
    if (profile) {
      setSpeakerReferencePath(profile.referencePath);
      setSpeakerProfileName(profile.name);
      setError(null);
    }
  };

  const setOutputMode = (value: LiveOutputMode) => {
    if (activeLiveSessionId) {
      setError("Stop the current live session before changing the output mode.");
      return;
    }

    if (value === "virtualMic") {
      if (!virtualMicStatus?.installed || !virtualMicStatus.playbackDeviceId) {
        setError(virtualMicStatus?.message ?? "VB-CABLE was not detected. Install it, then refresh devices.");
        setOutputModeState("monitor");
        return;
      }
    }

    setOutputModeState(value);
    setError(null);
  };

  const browseInputPath = async () => {
    const nextPath = await browseForAudioInput();
    if (nextPath) {
      setInputPath(nextPath);
    }
  };

  const browseOutputPath = async () => {
    const nextPath = await browseForOutputWav();
    if (nextPath) {
      setOutputPath(nextPath);
    }
  };

  const browseSpeakerInputPath = async () => {
    const nextPath = await browseForAudioInput();
    if (nextPath) {
      setSpeakerInputPath(nextPath);
    }
  };

  const browseSpeakerReferencePath = async () => {
    const nextPath = await browseForAudioInput();
    if (nextPath) {
      updateSpeakerReferencePath(nextPath);
    }
  };

  const browseSpeakerOutputPath = async () => {
    const nextPath = await browseForOutputWav();
    if (nextPath) {
      setSpeakerOutputPath(nextPath);
    }
  };

  const browseDebugInputPath = async () => {
    const nextPath = await browseForAudioInput();
    if (nextPath) {
      setDebugInputPath(nextPath);
    }
  };

  const browseRecordOutputPath = async () => {
    const nextPath = await browseForOutputWav();
    if (nextPath) {
      setRecordOutputPath(nextPath);
    }
  };

  const startOffline = async () => {
    if (!inputPath.trim()) {
      setError("Choose an input audio file before starting the offline render.");
      return;
    }
    if (!outputPath.trim()) {
      setError("Choose an output WAV path before starting the offline render.");
      return;
    }
    if (selectedCategories.length === 0) {
      setError("Select at least one model category to suppress.");
      return;
    }

    setError(null);
    setIsOfflineRunning(true);
    setOfflineProgress(null);

    try {
      let finishedBeforeResolve = false;
      const result = await startOfflineJob(
        {
          inputPath,
          outputPath,
          categories: selectedCategories,
          aggressiveness,
        },
        (event) => {
          setOfflineProgress(event);
          if (event.stage === "completed" || event.stage === "failed" || event.stage === "cancelled") {
            finishedBeforeResolve = true;
            setIsOfflineRunning(false);
            setActiveOfflineJobId(null);
          }
        },
      );
      if (!finishedBeforeResolve) {
        setActiveOfflineJobId(result.jobId);
      }
    } catch (jobError) {
      setIsOfflineRunning(false);
      setError(jobError instanceof Error ? jobError.message : "Offline processing failed to start.");
    } finally {
      await refreshRuntimeMetrics();
    }
  };

  const startSpeakerSuppression = async () => {
    if (!speakerInputPath.trim()) {
      setError("Choose a mixture audio file before starting speaker suppression.");
      return;
    }
    if (!speakerReferencePath.trim()) {
      setError("Choose a reference speaker clip before starting speaker suppression.");
      return;
    }
    if (!speakerOutputPath.trim()) {
      setError("Choose an output WAV path before starting speaker suppression.");
      return;
    }
    if (speakerEngine === "clearvoice_bundle" && targetSpeakerInfo && !targetSpeakerInfo.clearvoiceReady) {
      setError("The ClearVoice quality bundle is present but its Python runtime is not installed yet.");
      return;
    }

    setError(null);
    setIsOfflineRunning(true);
    setOfflineProgress(null);

    try {
      let finishedBeforeResolve = false;
      const result = await startTargetSpeakerJob(
        {
          inputPath: speakerInputPath,
          referencePath: speakerReferencePath,
          outputPath: speakerOutputPath,
          engine: speakerEngine,
          outputMode: speakerOutputMode,
          removalScale: speakerRemovalScale,
        },
        (event) => {
          setOfflineProgress(event);
          if (event.stage === "completed" || event.stage === "failed" || event.stage === "cancelled") {
            finishedBeforeResolve = true;
            setIsOfflineRunning(false);
            setActiveOfflineJobId(null);
          }
        },
      );
      if (!finishedBeforeResolve) {
        setActiveOfflineJobId(result.jobId);
      }
    } catch (jobError) {
      setIsOfflineRunning(false);
      setError(jobError instanceof Error ? jobError.message : "Speaker suppression failed to start.");
    } finally {
      await Promise.all([refreshRuntimeMetrics(), refreshTargetSpeakerInfo()]);
    }
  };

  const saveCurrentSpeakerProfile = async () => {
    if (!speakerProfileName.trim()) {
      setError("Enter a speaker profile name before saving.");
      return;
    }
    if (!speakerReferencePath.trim()) {
      setError("Choose a reference speaker clip before saving a profile.");
      return;
    }

    try {
      const profile = await saveSpeakerProfileApi({
        name: speakerProfileName,
        referencePath: speakerReferencePath,
      });
      setSpeakerProfiles((current) => {
        const withoutExisting = current.filter((item) => item.id !== profile.id);
        return [...withoutExisting, profile].sort((left, right) => left.name.localeCompare(right.name));
      });
      setSelectedSpeakerProfileIdState(profile.id);
      setSpeakerReferencePath(profile.referencePath);
      setSpeakerProfileName(profile.name);
      setError(null);
    } catch (profileError) {
      setError(profileError instanceof Error ? profileError.message : "Unable to save speaker profile.");
    }
  };

  const deleteSelectedSpeakerProfile = async () => {
    if (!selectedSpeakerProfileId) {
      setError("Choose a saved speaker profile before deleting.");
      return;
    }

    try {
      await deleteSpeakerProfileApi({ profileId: selectedSpeakerProfileId });
      setSpeakerProfiles((current) => current.filter((profile) => profile.id !== selectedSpeakerProfileId));
      setSelectedSpeakerProfileIdState("");
      setError(null);
    } catch (profileError) {
      setError(profileError instanceof Error ? profileError.message : "Unable to delete speaker profile.");
    }
  };

  const cancelCurrentOffline = async () => {
    if (!activeOfflineJobId) {
      return;
    }

    try {
      await cancelOfflineJob({ jobId: activeOfflineJobId });
      setOfflineProgress((current) =>
        current
          ? { ...current, stage: "cancelled", message: "Cancellation requested." }
          : null,
      );
      setIsOfflineRunning(false);
      setActiveOfflineJobId(null);
    } catch (jobError) {
      setError(jobError instanceof Error ? jobError.message : "Unable to cancel the offline job.");
    } finally {
      await refreshRuntimeMetrics();
    }
  };

  const startLive = async () => {
    const speakerLive = desktopMode === "speakerSuppression";
    if (!speakerLive && selectedCategories.length === 0) {
      setError("Select at least one model category before starting live monitoring.");
      return;
    }
    if (speakerLive && !speakerReferencePath.trim()) {
      setError("Choose a reference speaker clip or saved speaker profile before starting speaker realtime.");
      return;
    }
    if (speakerLive && speakerEngine !== "tsextract_onnx") {
      setError("The Quality Bundle engine is offline-only. Use Fast ONNX for speaker realtime.");
      return;
    }
    if (debugInputEnabled && !debugInputPath.trim()) {
      setError("Choose a debug input WAV path or turn the debug WAV mic source off.");
      return;
    }
    if (recordEnabled && !recordOutputPath.trim()) {
      setError("Choose a record output WAV path or turn live recording off.");
      return;
    }
    if (outputMode === "virtualMic" && (!virtualMicStatus?.installed || !virtualMicStatus.playbackDeviceId)) {
      setError(virtualMicStatus?.message ?? "VB-CABLE was not detected. Install it, then refresh devices.");
      return;
    }

    setError(null);
    setIsStartingLive(true);
    setLiveMeter(null);

    try {
      let endedBeforeResolve = false;
      const result = await startLiveMonitor(
        {
          processingMode: speakerLive ? "speakerSuppression" : "semanticSuppression",
          inputDeviceId: inputDeviceId || null,
          outputDeviceId:
            outputMode === "virtualMic"
              ? virtualMicStatus?.playbackDeviceId ?? null
              : outputDeviceId || null,
          outputMode,
          debugInputPath: debugInputEnabled ? debugInputPath : null,
          categories: speakerLive ? [] : selectedCategories,
          aggressiveness,
          lookaheadMs,
          recordOutputPath: recordEnabled ? recordOutputPath : null,
          speakerReferencePath: speakerLive ? speakerReferencePath : null,
          speakerEngine: speakerLive ? speakerEngine : null,
          speakerOutputMode: speakerLive ? speakerOutputMode : null,
          speakerRemovalScale: speakerLive ? speakerRemovalScale : null,
        },
        {
          onStatus: (event) => {
            setLiveStatus(event);
            if (event.state === "stopped" || event.state === "error") {
              endedBeforeResolve = true;
              setActiveLiveSessionId(null);
            }
          },
          onMeter: (event) => {
            setLiveMeter(event);
          },
        },
      );
      if (!endedBeforeResolve) {
        setActiveLiveSessionId(result.sessionId);
      }
    } catch (liveError) {
      setError(liveError instanceof Error ? liveError.message : "Unable to start live monitoring.");
    } finally {
      setIsStartingLive(false);
      await refreshRuntimeMetrics();
    }
  };

  const stopLive = async () => {
    if (!activeLiveSessionId) {
      return;
    }

    try {
      await stopLiveMonitor({ sessionId: activeLiveSessionId });
      setLiveStatus((current) =>
        current
          ? { ...current, state: "stopped", message: "Live monitoring stopped." }
          : INITIAL_LIVE_STATUS,
      );
      setActiveLiveSessionId(null);
    } catch (liveError) {
      setError(liveError instanceof Error ? liveError.message : "Unable to stop the live session.");
    } finally {
      await refreshRuntimeMetrics();
    }
  };

  const contextValue = useMemo<DesktopRuntimeContextValue>(
    () => ({
      categories,
      presets,
      devices,
      runtimeMetrics,
      targetSpeakerInfo,
      speakerProfiles,
      virtualMicStatus,
      desktopMode,
      selectedCategories,
      aggressiveness,
      speakerInputPath,
      speakerReferencePath,
      speakerOutputPath,
      speakerEngine,
      speakerOutputMode,
      speakerRemovalScale,
      selectedSpeakerProfileId,
      speakerProfileName,
      lookaheadMs,
      outputMode,
      inputDeviceId,
      outputDeviceId,
      inputPath,
      outputPath,
      debugInputEnabled,
      debugInputPath,
      recordEnabled,
      recordOutputPath,
      liveStatus,
      liveMeter,
      offlineProgress,
      activeLiveSessionId,
      activeOfflineJobId,
      isLoading,
      isStartingLive,
      isOfflineRunning,
      error,
      setDesktopMode,
      setSelectedCategories,
      toggleCategory,
      applyPreset,
      setAggressiveness,
      setSpeakerInputPath,
      setSpeakerReferencePath: updateSpeakerReferencePath,
      setSpeakerOutputPath,
      setSpeakerEngine,
      setSpeakerOutputMode,
      setSpeakerRemovalScale,
      setSelectedSpeakerProfileId,
      setSpeakerProfileName,
      setLookaheadMs,
      setOutputMode,
      setInputDeviceId,
      setOutputDeviceId,
      setInputPath,
      setOutputPath,
      setDebugInputEnabled,
      setDebugInputPath,
      setRecordEnabled,
      setRecordOutputPath,
      browseInputPath,
      browseOutputPath,
      browseSpeakerInputPath,
      browseSpeakerReferencePath,
      browseSpeakerOutputPath,
      browseDebugInputPath,
      browseRecordOutputPath,
      refreshDevices,
      refreshVirtualMicStatus,
      refreshRuntimeMetrics,
      refreshTargetSpeakerInfo,
      refreshSpeakerProfiles,
      startOffline,
      startSpeakerSuppression,
      saveCurrentSpeakerProfile,
      deleteSelectedSpeakerProfile,
      cancelOffline: cancelCurrentOffline,
      startLive,
      stopLive,
      clearError: () => setError(null),
    }),
    [
      activeLiveSessionId,
      activeOfflineJobId,
      aggressiveness,
      categories,
      desktopMode,
      devices,
      error,
      debugInputEnabled,
      debugInputPath,
      inputDeviceId,
      inputPath,
      isLoading,
      isOfflineRunning,
      isStartingLive,
      liveMeter,
      liveStatus,
      lookaheadMs,
      offlineProgress,
      outputMode,
      outputDeviceId,
      outputPath,
      presets,
      recordEnabled,
      recordOutputPath,
      runtimeMetrics,
      selectedCategories,
      selectedSpeakerProfileId,
      speakerProfileName,
      speakerEngine,
      speakerInputPath,
      speakerOutputMode,
      speakerOutputPath,
      speakerProfiles,
      speakerReferencePath,
      speakerRemovalScale,
      targetSpeakerInfo,
      virtualMicStatus,
    ],
  );

  return (
    <DesktopRuntimeContext.Provider value={contextValue}>
      {children}
    </DesktopRuntimeContext.Provider>
  );
};

export const useDesktopRuntime = () => {
  const context = useContext(DesktopRuntimeContext);
  if (!context) {
    throw new Error("useDesktopRuntime must be used within DesktopRuntimeProvider");
  }
  return context;
};
