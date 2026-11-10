import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { WordCaption } from '../types';

interface WordCaptionsProps {
  captions?: WordCaption[];
}

export const WordCaptions: React.FC<WordCaptionsProps> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!captions || captions.length === 0) {
    return null;
  }

  const currentMs = (frame / fps) * 1000;

  // Window of 5-6 words around current time
  const currentIndex = captions.findIndex(
    (c) => currentMs >= c.startMs && currentMs <= c.endMs
  );

  const activeIdx = currentIndex !== -1 ? currentIndex : 0;
  const startIdx = Math.max(0, activeIdx - 2);
  const endIdx = Math.min(captions.length, activeIdx + 4);
  const visibleWords = captions.slice(startIdx, endIdx);

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
