const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const path = require("path");
const fs = require("fs");

const config = getDefaultConfig(__dirname);

// Fix for workspace root: prevent Metro from watching non-existent root node_modules
const rootNodeModules = path.resolve(__dirname, "..", "node_modules");
if (!fs.existsSync(rootNodeModules)) {
  // If root node_modules doesn't exist, ensure it's not in watchFolders
  config.watchFolders = (config.watchFolders || []).filter(
    (folder) => folder !== rootNodeModules && !folder.startsWith(rootNodeModules + path.sep)
  );
  
  // Add to blockList to prevent any attempts to watch it
  config.resolver = {
    ...config.resolver,
    blockList: [
      ...(config.resolver?.blockList || []),
      new RegExp(rootNodeModules.replace(/\\/g, "\\\\").replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ".*"),
    ],
  };
}

module.exports = withNativeWind(config, {
  input: "./global.css",
  // Force write CSS to file system instead of virtual modules
  // This fixes iOS styling issues in development mode
  forceWriteFileSystem: true,
});
