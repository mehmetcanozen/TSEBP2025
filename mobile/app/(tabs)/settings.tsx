import React, { useState, useEffect } from "react";
import { ScrollView, Text, View, Pressable, Switch, useColorScheme as useSystemColorScheme, Alert, Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import { useThemeContext } from "@/lib/theme-provider";
import { useAuth } from "@/hooks/use-auth";
import AudioService from "@/src/services/AudioService";
import NotificationService from "@/src/services/NotificationService";
import { cn } from "@/lib/utils";

type AudioQuality = "high" | "medium" | "low";
type ThemeMode = "light" | "dark" | "auto";

export default function SettingsScreen() {
  const colors = useColors();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { setColorScheme } = useThemeContext();
  const systemColorScheme = useSystemColorScheme();
  const [audioQuality, setAudioQuality] = useState<AudioQuality>("high");
  const [themeMode, setThemeMode] = useState<ThemeMode>("auto");
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  useEffect(() => {
    loadSettings();
    // Initialize notification service only on native platforms
    if (Platform.OS !== "web") {
      NotificationService.initialize().catch((error) => {
        console.warn("Failed to initialize notification service:", error);
      });
    }
  }, []);

  // Listen to system theme changes when in auto mode
  useEffect(() => {
    if (themeMode === "auto") {
      const scheme = systemColorScheme ?? "light";
      setColorScheme(scheme);
    }
  }, [systemColorScheme, themeMode, setColorScheme]);

  const loadSettings = async () => {
    try {
      const quality = (await AsyncStorage.getItem("audioQuality")) as AudioQuality;
      const theme = (await AsyncStorage.getItem("themeMode")) as ThemeMode;
      const notifications = await AsyncStorage.getItem("notificationsEnabled");

      if (quality) {
        setAudioQuality(quality);
        AudioService.setAudioQuality(quality);
      }
      if (theme) {
        setThemeMode(theme);
        applyTheme(theme);
      } else {
        // Apply default theme if none saved
        applyTheme("auto");
      }
      if (notifications !== null) setNotificationsEnabled(notifications === "true");
    } catch (error) {
      console.error("Error loading settings:", error);
    }
  };

  const applyTheme = (theme: ThemeMode) => {
    if (theme === "auto") {
      const scheme = systemColorScheme ?? "light";
      setColorScheme(scheme);
    } else {
      setColorScheme(theme);
    }
  };

  const saveSettings = async (key: string, value: string | boolean) => {
    try {
      await AsyncStorage.setItem(key, String(value));
    } catch (error) {
      console.error("Error saving settings:", error);
    }
  };

  const handleAudioQualityChange = (quality: AudioQuality) => {
    setAudioQuality(quality);
    saveSettings("audioQuality", quality);
    // Apply audio quality to AudioService
    AudioService.setAudioQuality(quality);
    console.log("Audio quality changed to:", quality);
  };

  const handleThemeModeChange = (theme: ThemeMode) => {
    setThemeMode(theme);
    saveSettings("themeMode", theme);
    applyTheme(theme);
  };

  const handleNotificationsToggle = async (value: boolean) => {
    setNotificationsEnabled(value);
    saveSettings("notificationsEnabled", value);
    
    // Only use NotificationService on native platforms
    if (Platform.OS !== "web") {
      try {
        await NotificationService.setNotificationsEnabled(value);

        // Show test notification when enabling
        if (value) {
          setTimeout(() => {
            NotificationService.sendNotification(
              "Notifications Enabled",
              "You will now receive notifications from Semantic Noise Mixer"
            ).catch((error) => {
              console.warn("Failed to send notification:", error);
            });
          }, 500);
        } else {
          Alert.alert(
            "Notifications Disabled",
            "You will no longer receive notifications from this app."
          );
        }
      } catch (error) {
        console.warn("Notification service error:", error);
      }
    } else {
      // Web platform: just show a message
      if (value) {
        Alert.alert(
          "Notifications Enabled",
          "Notification settings saved. Note: Push notifications are not available on web platform."
        );
      } else {
        Alert.alert(
          "Notifications Disabled",
          "Notifications have been disabled."
        );
      }
    }
  };

  const QualityButton = ({
    quality,
    label,
  }: {
    quality: AudioQuality;
    label: string;
  }) => {
    const isSelected = audioQuality === quality;
    return (
      <Pressable
        onPress={() => handleAudioQualityChange(quality)}
        style={({ pressed }) => [
          {
            flex: 1,
            paddingVertical: 12,
            paddingHorizontal: 16,
            borderRadius: 8,
            backgroundColor: isSelected ? colors.primary : colors.surface,
            borderWidth: isSelected ? 0 : 1,
            borderColor: colors.border,
            opacity: pressed ? 0.8 : 1,
          },
        ]}
      >
        <Text
          style={{
            textAlign: "center",
            fontWeight: "600",
            color: isSelected ? "#FFFFFF" : colors.foreground,
          }}
        >
          {label}
        </Text>
      </Pressable>
    );
  };

  const ThemeButton = ({ theme, label }: { theme: ThemeMode; label: string }) => {
    const isSelected = themeMode === theme;
    return (
      <Pressable
        onPress={() => handleThemeModeChange(theme)}
        style={({ pressed }) => [
          {
            flex: 1,
            paddingVertical: 12,
            paddingHorizontal: 16,
            borderRadius: 8,
            backgroundColor: isSelected ? colors.primary : colors.surface,
            borderWidth: isSelected ? 0 : 1,
            borderColor: colors.border,
            opacity: pressed ? 0.8 : 1,
          },
        ]}
      >
        <Text
          style={{
            textAlign: "center",
            fontWeight: "600",
            color: isSelected ? "#FFFFFF" : colors.foreground,
          }}
        >
          {label}
        </Text>
      </Pressable>
    );
  };

  return (
    <ScreenContainer className="p-4">
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <View className="gap-6">
          {/* Header */}
          <View className="gap-2">
            <Text className="text-3xl font-bold text-foreground">Settings</Text>
            <Text className="text-sm text-muted">
              Customize your app experience
            </Text>
          </View>

          {/* Account Section - Always visible */}
          <View className="bg-surface rounded-xl p-4 gap-3 border border-border">
            <Text className="text-lg font-semibold text-foreground">
              Account
            </Text>
            {user ? (
              <>
                <View className="gap-3">
                  <View className="flex-row justify-between items-center">
                    <Text className="text-sm text-muted">Name</Text>
                    <Text className="text-sm font-semibold text-foreground">
                      {user.name || "N/A"}
                    </Text>
                  </View>
                  <View className="flex-row justify-between items-center">
                    <Text className="text-sm text-muted">Email</Text>
                    <Text className="text-sm font-semibold text-foreground">
                      {user.email || "N/A"}
                    </Text>
                  </View>
                </View>
                <Pressable
                  onPress={async () => {
                    Alert.alert(
                      "Sign Out",
                      "Are you sure you want to sign out?",
                      [
                        { text: "Cancel", style: "cancel" },
                        {
                          text: "Sign Out",
                          style: "destructive",
                          onPress: async () => {
                            await logout();
                            router.replace("/(auth)/signin");
                          },
                        },
                      ]
                    );
                  }}
                  style={({ pressed }) => [
                    {
                      backgroundColor: colors.error,
                      padding: 14,
                      borderRadius: 8,
                      alignItems: "center",
                      opacity: pressed ? 0.8 : 1,
                      marginTop: 4,
                    },
                  ]}
                >
                  <Text className="text-white font-semibold text-base">
                    Sign Out
                  </Text>
                </Pressable>
              </>
            ) : (
              <View className="gap-3">
                <Text className="text-sm text-muted text-center">
                  You are not logged in
                </Text>
                <Pressable
                  onPress={() => {
                    router.push("/(auth)/signin");
                  }}
                  style={({ pressed }) => [
                    {
                      backgroundColor: colors.primary,
                      padding: 14,
                      borderRadius: 8,
                      alignItems: "center",
                      opacity: pressed ? 0.8 : 1,
                      marginTop: 4,
                    },
                  ]}
                >
                  <Text className="text-white font-semibold text-base">
                    Sign In
                  </Text>
                </Pressable>
              </View>
            )}
          </View>

          {/* Audio Quality Section */}
          <View className="bg-surface rounded-xl p-4 gap-3">
            <Text className="text-sm font-semibold text-foreground">
              Audio Quality
            </Text>
            <Text className="text-xs text-muted">
              Higher quality uses more battery
            </Text>
            <View className="flex-row gap-2">
              <QualityButton quality="low" label="Low" />
              <QualityButton quality="medium" label="Medium" />
              <QualityButton quality="high" label="High" />
            </View>
          </View>

          {/* Theme Section */}
          <View className="bg-surface rounded-xl p-4 gap-3">
            <Text className="text-sm font-semibold text-foreground">
              Theme
            </Text>
            <Text className="text-xs text-muted">
              Choose your preferred color scheme
            </Text>
            <View className="flex-row gap-2">
              <ThemeButton theme="light" label="Light" />
              <ThemeButton theme="dark" label="Dark" />
              <ThemeButton theme="auto" label="Auto" />
            </View>
          </View>

          {/* Notifications Section */}
          <View className="bg-surface rounded-xl p-4 flex-row justify-between items-center">
            <View className="flex-1">
              <Text className="text-sm font-semibold text-foreground">
                Notifications
              </Text>
              <Text className="text-xs text-muted mt-1">
                Receive app notifications
              </Text>
            </View>
            <Switch
              value={notificationsEnabled}
              onValueChange={handleNotificationsToggle}
              trackColor={{ false: colors.border, true: colors.primary }}
            />
          </View>

          {/* About Section */}
          <View className="bg-surface rounded-xl p-4 gap-3">
            <Text className="text-sm font-semibold text-foreground">
              About
            </Text>
            <View className="gap-2">
              <View className="flex-row justify-between">
                <Text className="text-sm text-muted">App Version</Text>
                <Text className="text-sm font-semibold text-foreground">
                  1.0.0
                </Text>
              </View>
              <View className="flex-row justify-between">
                <Text className="text-sm text-muted">Build</Text>
                <Text className="text-sm font-semibold text-foreground">
                  2024.01
                </Text>
              </View>
            </View>
          </View>

          {/* Info Section */}
          <View className="bg-surface rounded-xl p-4 gap-2">
            <Text className="text-xs text-muted leading-relaxed">
              Semantic Noise Mixer is a real-time audio processing application
              that uses AI to detect and separate different audio components
              including speech, background noise, and environmental events.
            </Text>
          </View>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}
