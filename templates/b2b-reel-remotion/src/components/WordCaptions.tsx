import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { WordCaption } from '../types';

interface WordCaptionsProps {
  captions?: WordCaption[];
}

export interface CaptionWindow {
  visibleWords: WordCaption[];
  startIdx: number;
}

export function getActiveCaptionWindow(
  captions?: WordCaption[],
  timeMs: number = 0
): CaptionWindow | null {
  if (!captions || captions.length === 0) {
    return null;
  }

  // Before speech starts:
  if (timeMs < captions[0].startMs) {
    return null;
  }

  // After the last word ends: ausblenden
  if (timeMs > captions[captions.length - 1].endMs) {
    return null;
  }

  // Find currently spoken word
  const currentIndex = captions.findIndex(
    (c) => timeMs >= c.startMs && timeMs <= c.endMs
  );

  let activeIdx: number;
  if (currentIndex !== -1) {
    activeIdx = currentIndex;
  } else {
    // In speech pauses between words: hold the last spoken word window
    let lastSpokenIdx = -1;
    for (let i = 0; i < captions.length; i++) {
      if (captions[i].endMs <= timeMs) {
        lastSpokenIdx = i;
      } else {
        break;
      }
    }
    if (lastSpokenIdx === -1) {
      return null;
    }
    activeIdx = lastSpokenIdx;
  }

  const startIdx = Math.max(0, activeIdx - 2);
  const endIdx = Math.min(captions.length, activeIdx + 4);
  return {
    visibleWords: captions.slice(startIdx, endIdx),
    startIdx,
  };
}

export const WordCaptions: React.FC<WordCaptionsProps> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentMs = (frame / fps) * 1000;
  const activeWindow = getActiveCaptionWindow(captions, currentMs);

  if (!activeWindow) {
    return null;
  }

  const { visibleWords, startIdx } = activeWindow;

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 120,
        left: 0,
        width: 1080,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 60px',
        boxSizing: 'border-box',
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '12px 16px',
          background: 'rgba(7, 9, 14, 0.75)',
          padding: '16px 28px',
          borderRadius: '20px',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        {visibleWords.map((item, i) => {
          const isCurrent = currentMs >= item.startMs && currentMs <= item.endMs;

          return (
            <span
              key={startIdx + i}
              style={{
                fontSize: '36px',
                fontWeight: isCurrent ? 900 : 700,
                color: isCurrent ? '#D4AF37' : '#FFFFFF',
                transform: isCurrent ? 'scale(1.1)' : 'scale(1)',
                textShadow: isCurrent ? '0 0 20px rgba(212,175,55,0.8)' : 'none',
                transition: 'all 0.1s ease-out',
                fontFamily: 'system-ui, -apple-system, sans-serif',
              }}
            >
              {item.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
