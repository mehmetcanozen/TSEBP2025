import React, { createContext, useContext, useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const RECORDINGS_KEY = 'SNS_RECORDINGS_V1';

export interface RecordingEntry {
  id: string;
  uri: string;
  category: string;
  categoryLabel: string;
  createdAt: number;
}

interface RecordingsContextType {
  recordings: RecordingEntry[];
  addRecording: (entry: RecordingEntry) => Promise<void>;
  deleteRecording: (id: string) => Promise<void>;
  clearAll: () => Promise<void>;
  reloadRecordings: () => Promise<void>;
}

const RecordingsContext = createContext<RecordingsContextType | undefined>(undefined);

export const RecordingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [recordings, setRecordings] = useState<RecordingEntry[]>([]);

  const load = useCallback(async () => {
    try {
      const raw = await AsyncStorage.getItem(RECORDINGS_KEY);
      if (raw) {
        setRecordings(JSON.parse(raw) as RecordingEntry[]);
      }
    } catch (e) {
      console.error('Failed to load recordings', e);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addRecording = useCallback(async (entry: RecordingEntry) => {
    setRecordings((prev) => {
      const next = [entry, ...prev];
      AsyncStorage.setItem(RECORDINGS_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const deleteRecording = useCallback(async (id: string) => {
    setRecordings((prev) => {
      const next = prev.filter((r) => r.id !== id);
      AsyncStorage.setItem(RECORDINGS_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const clearAll = useCallback(async () => {
    setRecordings([]);
    await AsyncStorage.removeItem(RECORDINGS_KEY);
  }, []);

  return (
    <RecordingsContext.Provider value={{ recordings, addRecording, deleteRecording, clearAll, reloadRecordings: load }}>
      {children}
    </RecordingsContext.Provider>
  );
};

export const useRecordings = () => {
  const context = useContext(RecordingsContext);
  if (!context) {
    throw new Error('useRecordings must be used within a RecordingsProvider');
  }
  return context;
};
