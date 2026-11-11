import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.classflow.app",
  appName: "Classflow",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
