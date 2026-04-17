declare module 'react-native-audio-record' {
  interface Options {
    sampleRate?: number;
    channels?: number;
    bitsPerSample?: number;
    audioSource?: number;
    wavFile?: string;
  }

  const AudioRecord: {
    init: (options: Options) => void;
    start: () => void;
    stop: () => Promise<string>;
    on: (event: 'data', callback: (data: string) => void) => void;
  };

  export default AudioRecord;
}
