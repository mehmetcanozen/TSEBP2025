import React, { useState, useEffect } from "react";
import {
  ScrollView,
  Text,
  View,
  Pressable,
  FlatList,
  Modal,
  TextInput,
  Alert,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import { cn } from "@/lib/utils";

interface Profile {
  id: string;
  name: string;
  speechGain: number;
  noiseGain: number;
  eventsGain: number;
  createdAt: string;
}

export default function ProfilesScreen() {
  const colors = useColors();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newProfileName, setNewProfileName] = useState("");
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      const stored = await AsyncStorage.getItem("profiles");
      if (stored) {
        setProfiles(JSON.parse(stored));
      }
    } catch (error) {
      console.error("Error loading profiles:", error);
    }
  };

  const saveProfiles = async (newProfiles: Profile[]) => {
    try {
      await AsyncStorage.setItem("profiles", JSON.stringify(newProfiles));
      setProfiles(newProfiles);
    } catch (error) {
      console.error("Error saving profiles:", error);
    }
  };

  const createProfile = () => {
    if (!newProfileName.trim()) {
      Alert.alert("Error", "Please enter a profile name");
      return;
    }

    const newProfile: Profile = {
      id: Date.now().toString(),
      name: newProfileName,
      speechGain: 1.0,
      noiseGain: 0.0,
      eventsGain: 0.5,
      createdAt: new Date().toISOString(),
    };

    saveProfiles([...profiles, newProfile]);
    setNewProfileName("");
    setShowModal(false);
  };

  const deleteProfile = (id: string) => {
    Alert.alert("Delete Profile", "Are you sure you want to delete this profile?", [
      { text: "Cancel", onPress: () => {} },
      {
        text: "Delete",
        onPress: () => {
          saveProfiles(profiles.filter((p) => p.id !== id));
        },
      },
    ]);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString();
  };

  const renderProfile = ({ item }: { item: Profile }) => (
    <View className="bg-surface rounded-lg p-4 border border-border mb-3">
      <View className="gap-3">
        <View className="flex-row justify-between items-start">
          <View className="flex-1">
            <Text className="text-lg font-semibold text-foreground">
              {item.name}
            </Text>
            <Text className="text-xs text-muted mt-1">
              Created: {formatDate(item.createdAt)}
            </Text>
          </View>
        </View>

        {/* Gain Values */}
        <View className="gap-2 bg-background rounded-lg p-3">
          <View className="flex-row justify-between">
            <Text className="text-sm text-muted">Speech</Text>
            <Text className="text-sm font-semibold text-foreground">
              {Math.round(item.speechGain * 100)}%
            </Text>
          </View>
          <View className="flex-row justify-between">
            <Text className="text-sm text-muted">Background</Text>
            <Text className="text-sm font-semibold text-foreground">
              {Math.round(item.noiseGain * 100)}%
            </Text>
          </View>
          <View className="flex-row justify-between">
            <Text className="text-sm text-muted">Events</Text>
            <Text className="text-sm font-semibold text-foreground">
              {Math.round(item.eventsGain * 100)}%
            </Text>
          </View>
        </View>

        {/* Actions */}
        <View className="flex-row gap-2">
          <Pressable
            onPress={() => setSelectedProfile(item)}
            style={({ pressed }) => [
              {
                flex: 1,
                paddingVertical: 10,
                paddingHorizontal: 12,
                borderRadius: 8,
                backgroundColor: colors.primary,
                opacity: pressed ? 0.8 : 1,
              },
            ]}
          >
            <Text className="text-center text-white font-semibold text-sm">
              Load
            </Text>
          </Pressable>
          <Pressable
            onPress={() => deleteProfile(item.id)}
            style={({ pressed }) => [
              {
                flex: 1,
                paddingVertical: 10,
                paddingHorizontal: 12,
                borderRadius: 8,
                backgroundColor: colors.error,
                opacity: pressed ? 0.8 : 1,
              },
            ]}
          >
            <Text className="text-center text-white font-semibold text-sm">
              Delete
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );

  return (
    <ScreenContainer className="p-4">
      <View className="flex-1 gap-4">
        {/* Header */}
        <View className="gap-2">
          <Text className="text-3xl font-bold text-foreground">Profiles</Text>
          <Text className="text-sm text-muted">
            Save and manage your audio mixing presets
          </Text>
        </View>

        {/* Create Button */}
        <Pressable
          onPress={() => setShowModal(true)}
          style={({ pressed }) => [
            {
              paddingVertical: 14,
              paddingHorizontal: 20,
              borderRadius: 10,
              backgroundColor: colors.primary,
              opacity: pressed ? 0.8 : 1,
            },
          ]}
        >
          <Text className="text-center text-white font-semibold">
            + Create New Profile
          </Text>
        </Pressable>

        {/* Profiles List */}
        {profiles.length === 0 ? (
          <View className="flex-1 items-center justify-center gap-3">
            <Text className="text-lg font-semibold text-foreground">
              No Profiles Yet
            </Text>
            <Text className="text-sm text-muted text-center">
              Create your first profile to save your audio mixing settings
            </Text>
          </View>
        ) : (
          <FlatList
            data={profiles}
            renderItem={renderProfile}
            keyExtractor={(item) => item.id}
            scrollEnabled={false}
          />
        )}
      </View>

      {/* Create Profile Modal */}
      <Modal
        visible={showModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowModal(false)}
      >
        <View className="flex-1 bg-black/50 items-center justify-center p-4">
          <View className="bg-surface rounded-2xl p-6 w-full max-w-sm gap-4 border border-border">
            <Text className="text-2xl font-bold text-foreground">
              New Profile
            </Text>

            <TextInput
              placeholder="Profile name (e.g., Quiet Room)"
              placeholderTextColor={colors.muted}
              value={newProfileName}
              onChangeText={setNewProfileName}
              style={{
                paddingVertical: 12,
                paddingHorizontal: 12,
                borderRadius: 8,
                borderWidth: 1,
                borderColor: colors.border,
                color: colors.foreground,
                fontSize: 16,
              }}
            />

            <View className="flex-row gap-3">
              <Pressable
                onPress={() => {
                  setShowModal(false);
                  setNewProfileName("");
                }}
                style={({ pressed }) => [
                  {
                    flex: 1,
                    paddingVertical: 12,
                    paddingHorizontal: 16,
                    borderRadius: 8,
                    backgroundColor: colors.border,
                    opacity: pressed ? 0.8 : 1,
                  },
                ]}
              >
                <Text className="text-center text-foreground font-semibold">
                  Cancel
                </Text>
              </Pressable>
              <Pressable
                onPress={createProfile}
                style={({ pressed }) => [
                  {
                    flex: 1,
                    paddingVertical: 12,
                    paddingHorizontal: 16,
                    borderRadius: 8,
                    backgroundColor: colors.primary,
                    opacity: pressed ? 0.8 : 1,
                  },
                ]}
              >
                <Text className="text-center text-white font-semibold">
                  Create
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </ScreenContainer>
  );
}
