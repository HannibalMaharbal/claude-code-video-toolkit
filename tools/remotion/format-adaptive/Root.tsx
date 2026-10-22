import React from 'react';
import {Composition} from 'remotion';
import {FormatAdaptive, formatAdaptiveDefaultProps, FormatAdaptiveProps} from './FormatAdaptive';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="FormatAdaptive"
    component={FormatAdaptive}
    fps={formatAdaptiveDefaultProps.videoFps}
    width={formatAdaptiveDefaultProps.videoWidth}
    height={formatAdaptiveDefaultProps.videoHeight}
    durationInFrames={formatAdaptiveDefaultProps.videoDurationInFrames}
    defaultProps={formatAdaptiveDefaultProps}
    calculateMetadata={async ({props}: {props: FormatAdaptiveProps}) => ({
      fps: props.videoFps,
      width: props.videoWidth,
      height: props.videoHeight,
      durationInFrames: props.videoDurationInFrames,
    })}
  />
);
