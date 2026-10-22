import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useVideoConfig} from 'remotion';

export type Cue = {
  text: string;
  startMs: number;
  endMs: number;
};

export type BackgroundBox = {
  color: string;
  paddingPx: number;
};

export type SubtitleStyle = {
  fontFamily: string;
  fontDataUri: string | null;
  fontSizePx: number;
  color: string;
  strokeColor: string | null;
  strokeWidthPx: number;
  position: 'top' | 'center' | 'bottom';
  offsetPx: number;
  backgroundBox: BackgroundBox | null;
  safeArea: {x: number; y: number; width: number; height: number} | null;
};

export type SubtitleBurnProps = {
  /** Filename inside the --public-dir passed to `remotion render`. */
  videoSrc: string;
  videoFps: number;
  videoWidth: number;
  videoHeight: number;
  videoDurationInFrames: number;
  cues: Cue[];
  style: SubtitleStyle;
};

export const subtitleBurnDefaultProps: SubtitleBurnProps = {
  videoSrc: '',
  videoFps: 30,
  videoWidth: 1920,
  videoHeight: 1080,
  videoDurationInFrames: 30,
  cues: [],
  style: {
    fontFamily: 'Arial',
    fontDataUri: null,
    fontSizePx: 42,
    color: '#ffffff',
    strokeColor: '#000000',
    strokeWidthPx: 2,
    position: 'bottom',
    offsetPx: 64,
    backgroundBox: null,
    safeArea: null,
  },
};

const CueOverlay: React.FC<{text: string; style: SubtitleStyle; fontFamily: string}> = ({
  text,
  style,
  fontFamily,
}) => {
  const justify =
    style.position === 'top' ? 'flex-start' : style.position === 'center' ? 'center' : 'flex-end';
  const textStyle: React.CSSProperties = {
    fontFamily,
    fontSize: style.fontSizePx,
    color: style.color,
    textAlign: 'center',
    whiteSpace: 'pre-wrap',
    WebkitTextStroke: style.strokeColor
      ? `${style.strokeWidthPx}px ${style.strokeColor}`
      : undefined,
    paintOrder: 'stroke fill',
  };
  const boxStyle: React.CSSProperties = style.backgroundBox
    ? {
        backgroundColor: style.backgroundBox.color,
        padding: style.backgroundBox.paddingPx,
        borderRadius: 6,
      }
    : {};
  const safeArea = style.safeArea;
  return (
    <AbsoluteFill
      style={{
        justifyContent: justify,
        alignItems: 'center',
        paddingTop: style.position === 'top' ? style.offsetPx : 0,
        paddingBottom: style.position === 'bottom' ? style.offsetPx : 0,
        left: safeArea?.x ?? 0,
        top: safeArea?.y ?? 0,
        right: safeArea ? undefined : 0,
        bottom: safeArea ? undefined : 0,
        width: safeArea?.width,
        height: safeArea?.height,
      }}
    >
      <div style={{...boxStyle, maxWidth: '100%'}}>
        <div style={textStyle}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};

export const SubtitleBurn: React.FC<SubtitleBurnProps> = ({videoSrc, cues, style}) => {
  const {fps} = useVideoConfig();
  const fontFamily = style.fontDataUri ? 'SubtitleBurnFont' : style.fontFamily;

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {style.fontDataUri ? (
        <style>{`@font-face{font-family:'SubtitleBurnFont';src:url(${style.fontDataUri});}`}</style>
      ) : null}
      {videoSrc ? <OffthreadVideo src={staticFile(videoSrc)} /> : null}
      {cues.map((cue, index) => {
        const from = Math.max(0, Math.round((cue.startMs / 1000) * fps));
        const durationInFrames = Math.max(1, Math.round(((cue.endMs - cue.startMs) / 1000) * fps));
        return (
          <Sequence key={`${index}-${cue.startMs}`} from={from} durationInFrames={durationInFrames}>
            <CueOverlay text={cue.text} style={style} fontFamily={fontFamily} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
