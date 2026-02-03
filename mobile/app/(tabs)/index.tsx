import React, { useState, useEffect } from "react";
import { ScrollView, Text, View, Pressable, ActivityIndicator } from "react-native";
import Slider from "@react-native-community/slider";
import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import NotificationService from "@/src/services/NotificationService";
import { cn } from "@/lib/utils";

interface DetectionResult {
  speech: number;
  noise: number;
  events: number;
}

export default function DashboardScreen() {
  const colors = useColors();
  const [isAutoMode, setIsAutoMode] = useState(true);
  const [speechGain, setSpeechGain] = useState(1.0);
  const [noiseGain, setNoiseGain] = useState(0.0);
  const [eventsGain, setEventsGain] = useState(0.5);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [detections, setDetections] = useState<DetectionResult>({
    speech: 0,
    noise: 0,
    events: 0,
  });

  const handleStartRecording = async () => {
    setIsRecording(true);
    // Simulating recording for 3 seconds
    setTimeout(() => {
      setIsRecording(false);
      setIsProcessing(true);
      // Simulate TFLite inference
      setTimeout(() => {
        const newDetections = {
          speech: Math.random() * 100,
          noise: Math.random() * 100,
          events: Math.random() * 100,
        };
        setDetections(newDetections);
        setIsProcessing(false);
        
        // Send notification when processing completes
        NotificationService.sendNotification(
          "Audio Processing Complete",
          `Detected: ${Math.round(newDetections.speech)}% speech, ${Math.round(newDetections.noise)}% noise, ${Math.round(newDetections.events)}% events`,
          { type: "processing_complete", detections: newDetections }
        );
      }, 500);
    }, 3000);
  };

  const handlePlayAudio = () => {
    // Placeholder for audio playback
    console.log("Playing processed audio with gains:", {
      speechGain,
      noiseGain,
      eventsGain,
    });
  };

  return (
    <ScreenContainer className="p-4">
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <View className="gap-6">
          {/* Header */}
          <View className="gap-2">
            <Text className="text-3xl font-bold text-foreground">
              Semantic Noise Mixer
            </Text>
            <Text className="text-sm text-muted">
              Real-time audio processing with AI detection
            </Text>
          </View>

          {/* Mode Toggle */}
          <View className="bg-surface rounded-xl p-4 gap-3">
            <Text className="text-sm font-semibold text-foreground">Mode</Text>
            <View className="flex-row gap-3">
              <Pressable
                onPress={() => setIsAutoMode(true)}
                style={({ pressed }) => [
                  {
                    flex: 1,
                    paddingVertical: 12,
                    paddingHorizontal: 16,
                    borderRadius: 8,
                    backgroundColor: isAutoMode ? colors.primary : colors.border,
                    opacity: pressed ? 0.8 : 1,
                  },
                ]}
              >
                <Text
                  className={cn(
                    "text-center font-semibold",
                    isAutoMode ? "text-white" : "text-foreground"
                  )}
                >
                  Auto
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setIsAutoMode(false)}
                style={({ pressed }) => [
                  {
                    flex: 1,
                    paddingVertical: 12,
                    paddingHorizontal: 16,
                    borderRadius: 8,
                    backgroundColor: !isAutoMode ? colors.primary : colors.border,
                    opacity: pressed ? 0.8 : 1,
                  },
                ]}
              >
                <Text
                  className={cn(
                    "text-center font-semibold",
                    !isAutoMode ? "text-white" : "text-foreground"
                  )}
                >
                  Manual
                </Text>
              </Pressable>
            </View>
          </View>

          {/* Detection Cards */}
          {isProcessing ? (
            <View className="bg-surface rounded-xl p-6 items-center justify-center gap-3">
              <ActivityIndicator size="large" color={colors.primary} />
              <Text className="text-sm text-muted">Processing audio...</Text>
            </View>
          ) : (
            <View className="gap-3">
              <Text className="text-sm font-semibold text-foreground">
                Detections
              </Text>
              <View className="gap-2">
                {/* Speech Card */}
                <View className="bg-surface rounded-lg p-4 border border-border">
                  <View className="flex-row justify-between items-center mb-2">
                    <Text className="font-semibold text-foreground">Speech</Text>
                    <Text className="text-sm font-bold text-speechColor">
                      {Math.round(detections.speech)}%
                    </Text>
                  </View>
                  <View
                    style={{
                      height: 6,
                      backgroundColor: colors.border,
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <View
                      style={{
                        height: "100%",
                        width: `${detections.speech}%`,
                        backgroundColor: "#4CAF50",
                      }}
                    />
                  </View>
                </View>

                {/* Noise Card */}
                <View className="bg-surface rounded-lg p-4 border border-border">
                  <View className="flex-row justify-between items-center mb-2">
                    <Text className="font-semibold text-foreground">
                      Background
                    </Text>
                    <Text className="text-sm font-bold text-noiseColor">
                      {Math.round(detections.noise)}%
                    </Text>
                  </View>
                  <View
                    style={{
                      height: 6,
                      backgroundColor: colors.border,
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <View
                      style={{
                        height: "100%",
                        width: `${detections.noise}%`,
                        backgroundColor: "#FF9800",
                      }}
                    />
                  </View>
                </View>

                {/* Events Card */}
                <View className="bg-surface rounded-lg p-4 border border-border">
                  <View className="flex-row justify-between items-center mb-2">
                    <Text className="font-semibold text-foreground">Events</Text>
                    <Text className="text-sm font-bold text-eventsColor">
                      {Math.round(detections.events)}%
                    </Text>
                  </View>
                  <View
                    style={{
                      height: 6,
                      backgroundColor: colors.border,
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <View
                      style={{
                        height: "100%",
                        width: `${detections.events}%`,
                        backgroundColor: "#2196F3",
                      }}
                    />
                  </View>
                </View>
              </View>
            </View>
          )}

          {/* Mixer Controls */}
          {!isAutoMode && (
            <View className="bg-surface rounded-xl p-4 gap-4">
              <Text className="text-sm font-semibold text-foreground">
                Gain Controls
              </Text>

              {/* Speech Gain */}
              <View className="gap-2">
                <View className="flex-row justify-between">
                  <Text className="text-sm text-foreground">Speech</Text>
                  <Text className="text-sm font-semibold text-foreground">
                    {Math.round(speechGain * 100)}%
                  </Text>
                </View>
                <Slider
                  style={{ height: 40 }}
                  minimumValue={0}
                  maximumValue={1}
                  value={speechGain}
                  onValueChange={setSpeechGain}
                  minimumTrackTintColor="#4CAF50"
                  maximumTrackTintColor={colors.border}
                />
              </View>

              {/* Noise Gain */}
              <View className="gap-2">
                <View className="flex-row justify-between">
                  <Text className="text-sm text-foreground">Background</Text>
                  <Text className="text-sm font-semibold text-foreground">
                    {Math.round(noiseGain * 100)}%
                  </Text>
                </View>
                <Slider
                  style={{ height: 40 }}
                  minimumValue={0}
                  maximumValue={1}
                  value={noiseGain}
                  onValueChange={setNoiseGain}
                  minimumTrackTintColor="#FF9800"
                  maximumTrackTintColor={colors.border}
                />
              </View>

              {/* Events Gain */}
              <View className="gap-2">
                <View className="flex-row justify-between">
                  <Text className="text-sm text-foreground">Events</Text>
                  <Text className="text-sm font-semibold text-foreground">
                    {Math.round(eventsGain * 100)}%
                  </Text>
                </View>
                <Slider
                  style={{ height: 40 }}
                  minimumValue={0}
                  maximumValue={1}
                  value={eventsGain}
                  onValueChange={setEventsGain}
                  minimumTrackTintColor="#2196F3"
                  maximumTrackTintColor={colors.border}
                />
              </View>
            </View>
          )}

          {/* Recording Controls */}
          <View className="gap-3">
            <Pressable
              onPress={handleStartRecording}
              disabled={isRecording || isProcessing}
              style={({ pressed }) => [
                {
                  paddingVertical: 16,
                  paddingHorizontal: 24,
                  borderRadius: 12,
                  backgroundColor: isRecording ? "#FF6B6B" : colors.primary,
                  opacity: pressed || isRecording || isProcessing ? 0.8 : 1,
                },
              ]}
            >
              <Text className="text-center text-white font-semibold text-base">
                {isRecording ? "Recording..." : "Start Recording"}
              </Text>
            </Pressable>

            <Pressable
              onPress={handlePlayAudio}
              disabled={detections.speech === 0 && detections.noise === 0}
              style={({ pressed }) => [
                {
                  paddingVertical: 16,
                  paddingHorizontal: 24,
                  borderRadius: 12,
                  backgroundColor: colors.primary,
                  opacity:
                    pressed || (detections.speech === 0 && detections.noise === 0)
                      ? 0.8
                      : 1,
                },
              ]}
            >
              <Text className="text-center text-white font-semibold text-base">
                Play Processed Audio
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}
