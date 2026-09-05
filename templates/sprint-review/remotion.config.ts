import { Config } from '@remotion/cli/config';
import path from 'path';

Config.setVideoImageFormat('png');
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer('angle');
Config.setOffthreadVideoCacheSizeInBytes(1024 * 1024 * 512);

// Ensure shared lib/ imports resolve packages from this project's node_modules
Config.overrideWebpackConfig((config) => {
  return {
    ...config,
    resolve: {
      ...config.resolve,
      modules: [
        path.resolve(__dirname, 'node_modules'),
        ...(config.resolve?.modules || ['node_modules']),
      ],
    },
  };
});
