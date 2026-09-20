import React from 'react';
import {Composition} from 'remotion';
import {SubtitleBurn, subtitleBurnDefaultProps, SubtitleBurnProps} from './SubtitleBurn';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="SubtitleBurn"
      component={SubtitleBurn}
      fps={subtitleBurnDefaultProps.videoFps}
      width={subtitleBurnDefaultProps.videoWidth}
      height={subtitleBurnDefaultProps.videoHeight}
      durationInFrames={subtitleBurnDefaultProps.videoDurationInFrames}
      defaultProps={subtitleBurnDefaultProps}
      calculateMetadata={async ({props}: {props: SubtitleBurnProps}) => ({
        fps: props.videoFps,
        width: props.videoWidth,
        height: props.videoHeight,
        durationInFrames: props.videoDurationInFrames,
      })}
    />
  );
};
