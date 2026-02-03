/**
 * NotificationService - Local Push Notifications
 * 
 * Handles:
 * - Requesting notification permissions
 * - Scheduling and sending local notifications
 * - Managing notification preferences
 */

import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

// Configure notification behavior
// This must be called before any notification operations (native only)
if (Platform.OS !== "web") {
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
      }),
    });
  } catch (error) {
    console.warn("Failed to set notification handler:", error);
  }
}

class NotificationService {
  private isEnabled: boolean = true;
  private hasPermission: boolean = false;

  /**
   * Request notification permissions
   */
  async requestPermissions(): Promise<boolean> {
    // Web platform doesn't support push notifications
    if (Platform.OS === "web") {
      console.log("Notifications not supported on web platform");
      return false;
    }

    try {
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      if (existingStatus !== "granted") {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }

      this.hasPermission = finalStatus === "granted";
      return this.hasPermission;
    } catch (error) {
      console.error("Failed to request notification permissions:", error);
      return false;
    }
  }

  /**
   * Check if notifications are enabled
   */
  async isNotificationsEnabled(): Promise<boolean> {
    try {
      const enabled = await AsyncStorage.getItem("notificationsEnabled");
      if (enabled !== null) {
        this.isEnabled = enabled === "true";
      }
      return this.isEnabled;
    } catch (error) {
      console.error("Failed to check notification settings:", error);
      return this.isEnabled;
    }
  }

  /**
   * Set notification enabled state
   */
  async setNotificationsEnabled(enabled: boolean): Promise<void> {
    try {
      this.isEnabled = enabled;
      await AsyncStorage.setItem("notificationsEnabled", String(enabled));
      
      if (enabled) {
        // Request permissions when enabling
        await this.requestPermissions();
      }
    } catch (error) {
      console.error("Failed to save notification settings:", error);
    }
  }

  /**
   * Send a local notification
   */
  async sendNotification(
    title: string,
    body: string,
    data?: Record<string, any>
  ): Promise<string | null> {
    // Web platform doesn't support push notifications
    if (Platform.OS === "web") {
      console.log("Notifications not supported on web platform");
      return null;
    }

    try {
      // Check if notifications are enabled
      const enabled = await this.isNotificationsEnabled();
      if (!enabled) {
        console.log("Notifications are disabled, skipping notification");
        return null;
      }

      // Check permissions
      if (!this.hasPermission) {
        const hasPermission = await this.requestPermissions();
        if (!hasPermission) {
          console.warn("Notification permission not granted");
          return null;
        }
      }

      // Schedule notification
      const notificationId = await Notifications.scheduleNotificationAsync({
        content: {
          title,
          body,
          data,
          sound: true,
        },
        trigger: null, // Send immediately
      });

      console.log("Notification sent:", notificationId);
      return notificationId;
    } catch (error) {
      console.error("Failed to send notification:", error);
      return null;
    }
  }

  /**
   * Schedule a notification for later
   */
  async scheduleNotification(
    title: string,
    body: string,
    trigger: Notifications.NotificationTriggerInput,
    data?: Record<string, any>
  ): Promise<string | null> {
    try {
      const enabled = await this.isNotificationsEnabled();
      if (!enabled) {
        return null;
      }

      if (!this.hasPermission) {
        const hasPermission = await this.requestPermissions();
        if (!hasPermission) {
          return null;
        }
      }

      const notificationId = await Notifications.scheduleNotificationAsync({
        content: {
          title,
          body,
          data,
          sound: true,
        },
        trigger,
      });

      return notificationId;
    } catch (error) {
      console.error("Failed to schedule notification:", error);
      return null;
    }
  }

  /**
   * Cancel a scheduled notification
   */
  async cancelNotification(notificationId: string): Promise<void> {
    try {
      await Notifications.cancelScheduledNotificationAsync(notificationId);
    } catch (error) {
      console.error("Failed to cancel notification:", error);
    }
  }

  /**
   * Cancel all scheduled notifications
   */
  async cancelAllNotifications(): Promise<void> {
    try {
      await Notifications.cancelAllScheduledNotificationsAsync();
    } catch (error) {
      console.error("Failed to cancel all notifications:", error);
    }
  }

  /**
   * Get notification permission status
   */
  async getPermissionStatus(): Promise<Notifications.NotificationPermissionsStatus> {
    try {
      return await Notifications.getPermissionsAsync();
    } catch (error) {
      console.error("Failed to get permission status:", error);
      return { status: "undetermined", granted: false, canAskAgain: false };
    }
  }

  /**
   * Initialize notification service
   */
  async initialize(): Promise<void> {
    // Web platform doesn't support push notifications
    if (Platform.OS === "web") {
      console.log("Notification service initialization skipped on web platform");
      return;
    }

    try {
      await this.isNotificationsEnabled();
      await this.requestPermissions();
    } catch (error) {
      console.error("Failed to initialize notification service:", error);
    }
  }
}

export default new NotificationService();

