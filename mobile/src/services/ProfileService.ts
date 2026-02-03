/**
 * ProfileService - Audio Mixing Profile Management
 * 
 * Handles:
 * - Creating and saving audio mixing profiles
 * - Loading and applying profiles
 * - Deleting profiles
 * - Local storage with AsyncStorage
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

export interface Profile {
  id: string;
  name: string;
  speechGain: number;
  noiseGain: number;
  eventsGain: number;
  createdAt: string;
}

const PROFILES_STORAGE_KEY = "semantic_mixer_profiles";

class ProfileService {
  /**
   * Get all saved profiles
   */
  async getProfiles(): Promise<Profile[]> {
    try {
      const stored = await AsyncStorage.getItem(PROFILES_STORAGE_KEY);
      if (!stored) {
        return [];
      }
      return JSON.parse(stored);
    } catch (error) {
      console.error("Failed to load profiles:", error);
      return [];
    }
  }

  /**
   * Get a specific profile by ID
   */
  async getProfile(id: string): Promise<Profile | null> {
    try {
      const profiles = await this.getProfiles();
      return profiles.find((p) => p.id === id) || null;
    } catch (error) {
      console.error("Failed to get profile:", error);
      return null;
    }
  }

  /**
   * Create a new profile
   */
  async createProfile(
    name: string,
    speechGain: number,
    noiseGain: number,
    eventsGain: number
  ): Promise<Profile> {
    try {
      const profiles = await this.getProfiles();

      const newProfile: Profile = {
        id: Date.now().toString(),
        name,
        speechGain,
        noiseGain,
        eventsGain,
        createdAt: new Date().toISOString(),
      };

      profiles.push(newProfile);
      await AsyncStorage.setItem(PROFILES_STORAGE_KEY, JSON.stringify(profiles));

      console.log("Profile created:", newProfile.id);
      return newProfile;
    } catch (error) {
      console.error("Failed to create profile:", error);
      throw error;
    }
  }

  /**
   * Update an existing profile
   */
  async updateProfile(
    id: string,
    updates: Partial<Profile>
  ): Promise<Profile | null> {
    try {
      const profiles = await this.getProfiles();
      const index = profiles.findIndex((p) => p.id === id);

      if (index === -1) {
        console.warn("Profile not found:", id);
        return null;
      }

      const updatedProfile = {
        ...profiles[index],
        ...updates,
        id, // Ensure ID doesn't change
      };

      profiles[index] = updatedProfile;
      await AsyncStorage.setItem(PROFILES_STORAGE_KEY, JSON.stringify(profiles));

      console.log("Profile updated:", id);
      return updatedProfile;
    } catch (error) {
      console.error("Failed to update profile:", error);
      return null;
    }
  }

  /**
   * Delete a profile
   */
  async deleteProfile(id: string): Promise<boolean> {
    try {
      const profiles = await this.getProfiles();
      const filtered = profiles.filter((p) => p.id !== id);

      if (filtered.length === profiles.length) {
        console.warn("Profile not found:", id);
        return false;
      }

      await AsyncStorage.setItem(PROFILES_STORAGE_KEY, JSON.stringify(filtered));

      console.log("Profile deleted:", id);
      return true;
    } catch (error) {
      console.error("Failed to delete profile:", error);
      return false;
    }
  }

  /**
   * Clear all profiles
   */
  async clearProfiles(): Promise<void> {
    try {
      await AsyncStorage.removeItem(PROFILES_STORAGE_KEY);
      console.log("All profiles cleared");
    } catch (error) {
      console.error("Failed to clear profiles:", error);
    }
  }
}

export default new ProfileService();
