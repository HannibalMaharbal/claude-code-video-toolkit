import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile} from 'remotion';

export type TextElement = {
  id: string;
  content: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fontSize: number;
  maxLines: number;
  align: 'left' | 'center' | 'right';
  visible: boolean;
};

export type FormatAdaptiveProps = {
  videoSrc: string;
  videoFps: number;
  videoWidth: number;
  videoHeight: number;
  videoDurationInFrames: number;
  elements: TextElement[];
};

export const formatAdaptiveDefaultProps: FormatAdaptiveProps = {
  videoSrc: '', videoFps: 30, videoWidth: 1920, videoHeight: 1080,
  videoDurationInFrames: 30, elements: [],
};

export const FormatAdaptive: React.FC<FormatAdaptiveProps> = ({videoSrc, elements}) => (
  <AbsoluteFill style={{backgroundColor: 'black'}}>
    {videoSrc ? <OffthreadVideo src={staticFile(videoSrc)} /> : null}
    {elements.filter((element) => element.visible).map((element) => (
      <div key={element.id} style={{
        position: 'absolute', left: element.x, top: element.y, width: element.width,
        height: element.height, overflow: 'hidden', color: '#fff', fontFamily: 'Arial, sans-serif',
        fontWeight: 700, fontSize: element.fontSize, lineHeight: 1.18, textAlign: element.align,
        whiteSpace: 'pre-wrap', overflowWrap: 'break-word', textShadow: '0 2px 10px #000',
      }}>{element.content}</div>
    ))}
  </AbsoluteFill>
);
