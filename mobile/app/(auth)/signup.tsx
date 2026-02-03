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
import { getSignUpUrl } from "@/constants/oauth";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import * as Auth from "@/lib/_core/auth";


export default function SignUpScreen() {
  const colors = useColors();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleEmailSignUp = async () => {
    // Validation
    if (!name || !email || !password || !confirmPassword) {
      setError("Please fill in all fields");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // TODO: Implement email/password sign up API
      Alert.alert(
        "Email Sign Up",
        "Email/password registration will be implemented with backend API. Using OAuth for now.",
        [{ text: "OK" }]
      );

      // Fallback to OAuth
      handleOAuthSignUp();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthSignUp = async () => {
    try {
      const signUpUrl = getSignUpUrl();

      if (Platform.OS === "web") {
        window.location.href = signUpUrl;
      } else {
        const result = await WebBrowser.openAuthSessionAsync(signUpUrl);

        if (result.type === "success" && result.url) {
          await Linking.openURL(result.url);
        }
      }
    } catch (err) {
      // Fallback to demo login when OAuth is not configured
      try {
        await Auth.fakeOAuthLogin();
        router.replace("/(tabs)");
        return;
      } catch (e) {
        setError(err instanceof Error ? err.message : "OAuth sign up failed");
      }
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
          <View className="flex-1 justify-center p-6 gap-4">
            {/* Header */}
            <View className="gap-2">
              <Text className="text-3xl font-bold text-foreground">
                Create Account
              </Text>
              <Text className="text-sm text-muted">
                Sign up to get started with Semantic Noise Mixer
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

            {/* Name Input */}
            <View className="gap-2">
              <Text className="text-sm font-semibold text-foreground">
                Full Name
              </Text>
              <TextInput
                value={name}
                onChangeText={setName}
                placeholder="Enter your full name"
                placeholderTextColor={colors.muted}
                autoCapitalize="words"
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
                placeholder="Create a password"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoCapitalize="none"
                autoComplete="password-new"
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

            {/* Confirm Password Input */}
            <View className="gap-2">
              <Text className="text-sm font-semibold text-foreground">
                Confirm Password
              </Text>
              <TextInput
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                placeholder="Confirm your password"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoCapitalize="none"
                autoComplete="password-new"
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

            {/* Sign Up Button */}
            <Pressable
              onPress={handleEmailSignUp}
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
                  Sign Up
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

            {/* OAuth Sign Up Button */}
            <Pressable
              onPress={handleOAuthSignUp}
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

            {/* Sign In Link */}
            <View className="flex-row justify-center gap-2">
              <Text className="text-sm text-muted">
                Already have an account?
              </Text>
              <Pressable onPress={() => router.push("/(auth)/signin")}>
                <Text
                  style={{ color: colors.primary }}
                  className="text-sm font-semibold"
                >
                  Sign In
                </Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

