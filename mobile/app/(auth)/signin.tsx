import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from "react-native";
import { useRouter } from "expo-router";
import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import { useAuth } from "@/hooks/use-auth";
import * as Auth from "@/lib/_core/auth";
import * as Api from "@/lib/_core/api";
import { getLoginUrl, getSignUpUrl } from "@/constants/oauth";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";


export default function SignInScreen() {
  const colors = useColors();
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleEmailSignIn = async () => {
    if (!email || !password) {
      setError("Please enter both email and password");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // TODO: Implement email/password sign in API
      // For now, we'll use OAuth as fallback
      Alert.alert(
        "Email Sign In",
        "Email/password authentication will be implemented with backend API. Using OAuth for now.",
        [{ text: "OK" }]
      );

      // Fallback to OAuth
      handleOAuthSignIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  // const handleOAuthSignIn = async () => {
  //   try {
  //     const loginUrl = getLoginUrl();

  //     if (Platform.OS === "web") {
  //       // Web: redirect to OAuth
  //       window.location.href = loginUrl;
  //     } else {
  //       // Native: open in browser
  //       const result = await WebBrowser.openAuthSessionAsync(loginUrl);

  //       if (result.type === "success" && result.url) {
  //         // Deep link will handle the callback
  //         await Linking.openURL(result.url);
  //       }
  //     }
  //   } catch (err) {
  //     setError(err instanceof Error ? err.message : "OAuth sign in failed");
  //   }
  // };
  const handleOAuthSignIn = async () => {
    try {
      setLoading(true);
      setError(null);

      // Use fake OAuth login for development
      await Auth.fakeOAuthLogin();

      console.log("[SignIn] Fake login successful, redirecting...");

      // Redirect immediately without waiting for refresh
      setTimeout(() => {
        router.replace("/(tabs)");
      }, 100);
    } catch (err) {
      console.error("[SignIn] Error:", err);
      setError(err instanceof Error ? err.message : "Sign in failed");
      setLoading(false);
    }
  };




  return (
    <ScreenContainer className="flex-1">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        className="flex-1"
      >
        <ScrollView
          contentContainerStyle={{ flexGrow: 1 }}
          keyboardShouldPersistTaps="handled"
        >
          <View className="flex-1 justify-center p-6 gap-6">
            {/* Header */}
            <View className="gap-2">
              <Text className="text-3xl font-bold text-foreground">
                Welcome Back
              </Text>
              <Text className="text-sm text-muted">
                Sign in to continue to Semantic Noise Mixer
              </Text>
            </View>

            {/* Error Message */}
            {error && (
              <View
                className="bg-error/10 border border-error/20 rounded-lg p-3"
              >
                <Text className="text-sm text-error">{error}</Text>
              </View>
            )}

            {/* Email Input */}
            <View className="gap-2">
              <Text className="text-sm font-semibold text-foreground">
                Email
              </Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="Enter your email"
                placeholderTextColor={colors.muted}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
                style={{
                  backgroundColor: colors.surface,
                  borderWidth: 1,
                  borderColor: colors.border,
                  borderRadius: 8,
                  padding: 12,
                  color: colors.foreground,
                  fontSize: 16,
                }}
              />
            </View>

            {/* Password Input */}
            <View className="gap-2">
              <Text className="text-sm font-semibold text-foreground">
                Password
              </Text>
              <TextInput
                value={password}
                onChangeText={setPassword}
                placeholder="Enter your password"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoCapitalize="none"
                autoComplete="password"
                style={{
                  backgroundColor: colors.surface,
                  borderWidth: 1,
                  borderColor: colors.border,
                  borderRadius: 8,
                  padding: 12,
                  color: colors.foreground,
                  fontSize: 16,
                }}
              />
            </View>

            {/* Sign In Button */}
            <Pressable
              onPress={handleEmailSignIn}
              disabled={loading}
              style={({ pressed }) => [
                {
                  backgroundColor: colors.primary,
                  padding: 16,
                  borderRadius: 8,
                  alignItems: "center",
                  opacity: pressed || loading ? 0.8 : 1,
                },
              ]}
            >
              {loading ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text className="text-white font-semibold text-base">
                  Sign In
                </Text>
              )}
            </Pressable>

            {/* Divider */}
            <View className="flex-row items-center gap-4">
              <View
                style={{ flex: 1, height: 1, backgroundColor: colors.border }}
              />
              <Text className="text-sm text-muted">OR</Text>
              <View
                style={{ flex: 1, height: 1, backgroundColor: colors.border }}
              />
            </View>

            {/* OAuth Sign In Button */}
            <Pressable
              onPress={handleOAuthSignIn}
              style={({ pressed }) => [
                {
                  backgroundColor: colors.surface,
                  borderWidth: 1,
                  borderColor: colors.border,
                  padding: 16,
                  borderRadius: 8,
                  alignItems: "center",
                  opacity: pressed ? 0.8 : 1,
                },
              ]}
            >
              <Text className="text-foreground font-semibold text-base">
                Continue with OAuth
              </Text>
            </Pressable>

            {/* Sign Up Link */}
            <View className="flex-row justify-center gap-2">
              <Text className="text-sm text-muted">
                Don't have an account?
              </Text>
              <Pressable onPress={() => router.push("/(auth)/signup")}>
                <Text
                  style={{ color: colors.primary }}
                  className="text-sm font-semibold"
                >
                  Sign Up
                </Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

