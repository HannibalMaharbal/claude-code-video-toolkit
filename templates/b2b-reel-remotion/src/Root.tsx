import React from 'react';
import { Composition } from 'remotion';
import { B2BReel } from './B2BReel';
import sampleData from '../sample-data.json';
import { B2BReelData } from './types';

export const RemotionRoot: React.FC = () => {
  const data = sampleData as B2BReelData;
  const totalFrames = data.durationInSeconds * data.fps;

  return (
    <>
      <Composition
        id="B2BReel"
        component={B2BReel as React.FC}
        durationInFrames={totalFrames}
        fps={data.fps}
        width={1080}
        height={1920}
        defaultProps={{
          data,
        }}
      />
    </>
  );
};
