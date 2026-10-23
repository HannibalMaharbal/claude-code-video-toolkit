#!/usr/bin/env python3
"""
capcut_editor.py — Programmatic CapCut Desktop project manipulation.
Manipulates draft_content.json directly for autonomous rough cuts,
silence removal, dynamic punch-in zooms, and overlay tracks.

Based on CapCut Desktop macOS draft format.
"""

import os
import sys
import json
import shutil
import glob
import uuid
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

DEFAULT_CAPCUT_PATHS = [
    os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft"),
    os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Projects/com.lveditor.draft"),
    os.path.expanduser("~/Movies/CapCut App Video/User Data/Projects/com.lveditor.draft")
]

def find_capcut_project_root() -> Optional[Path]:
    """Locate the root directory where CapCut stores drafts."""
    for p in DEFAULT_CAPCUT_PATHS:
        path = Path(p)
        if path.exists():
            return path
    # If none exist yet, ensure the standard one
    std_path = Path(DEFAULT_CAPCUT_PATHS[0])
    std_path.mkdir(parents=True, exist_ok=True)
    return std_path

def list_projects() -> List[Dict[str, Any]]:
    """List all available CapCut projects."""
    root = find_capcut_project_root()
    if not root or not root.exists():
        return []
    
    projects = []
    for d in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if d.is_dir() and (d / "draft_content.json").exists():
            meta_file = d / "draft_meta_info.json"
            name = d.name
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        name = meta.get("draft_name", d.name)
                except Exception:
                    pass
            projects.append({
                "id": d.name,
                "name": name,
                "path": str(d),
                "modified": d.stat().st_mtime
            })
    return projects

class CapCutDraft:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.content_file = self.project_path / "draft_content.json"
        if not self.content_file.exists():
            raise FileNotFoundError(f"draft_content.json not found in {project_path}")
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self):
        with open(self.content_file, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def backup(self):
        bak_file = self.project_path / "draft_content.json.bak"
        shutil.copy2(self.content_file, bak_file)

    def save(self):
        self.backup()
        with open(self.content_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_tracks(self) -> List[Dict[str, Any]]:
        return self.data.get("tracks", [])

    def get_main_video_track(self) -> Optional[Dict[str, Any]]:
        for track in self.get_tracks():
            if track.get("type") == "video" and track.get("flag") == 0:
                return track
        for track in self.get_tracks():
            if track.get("type") == "video":
                return track
        return None

    def apply_punch_in_zooms(self, zoom_scale: float = 1.15, step: int = 2) -> int:
        """
        Applies alternating punch-in zoom (e.g. scale 1.15) to every Nth segment
        to eliminate monotonous talking-head shots without changing camera physically.
        """
        if step <= 0:
            raise ValueError("step must be greater than zero")
        if zoom_scale <= 0:
            raise ValueError("zoom_scale must be greater than zero")

        video_track = self.get_main_video_track()
        if not video_track:
            return 0
        
        segments = video_track.get("segments", [])
        modified_count = 0
        
        for idx, seg in enumerate(segments):
            if idx % step == 1:
                # Zoom in
                clip = seg.get("clip", {})
                scale = clip.get("scale", {})
                scale["x"] = zoom_scale
                scale["y"] = zoom_scale
                clip["scale"] = scale
                seg["clip"] = clip
                modified_count += 1
            else:
                # Reset zoom
                clip = seg.get("clip", {})
                scale = clip.get("scale", {})
                scale["x"] = 1.0
                scale["y"] = 1.0
                clip["scale"] = scale
                seg["clip"] = clip

        self.save()
        return modified_count

    def split_segment_at_micros(self, segment_idx: int, cut_time_micros: int) -> bool:
        """
        Splits a segment into two pieces at cut_time_micros (in microseconds relative to timeline).
        """
        video_track = self.get_main_video_track()
        if not video_track:
            return False
        
        segments = video_track.get("segments", [])
        if segment_idx >= len(segments):
            return False
            
        target_seg = segments[segment_idx]
        tr = target_seg.get("target_timerange", {})
        start = tr.get("start", 0)
        dur = tr.get("duration", 0)
        
        if cut_time_micros <= start or cut_time_micros >= start + dur:
            return False # cut point not in segment
            
        first_dur = cut_time_micros - start
        second_dur = dur - first_dur
        
        src_tr = target_seg.get("source_timerange", {})
        src_start = src_tr.get("start", 0)
        
        # Segment 1
        target_seg["target_timerange"]["duration"] = first_dur
        target_seg["source_timerange"]["duration"] = first_dur
        
        # Segment 2
        seg2 = json.loads(json.dumps(target_seg))
        seg2["id"] = str(uuid.uuid4()).upper()
        seg2["target_timerange"]["start"] = cut_time_micros
        seg2["target_timerange"]["duration"] = second_dur
        seg2["source_timerange"]["start"] = src_start + first_dur
        seg2["source_timerange"]["duration"] = second_dur
        
        segments.insert(segment_idx + 1, seg2)
        self.save()
        return True

    def remove_silence_ranges(self, silence_ranges_seconds: List[tuple]) -> int:
        """
        Given silence ranges in seconds [(start, end), ...], removes those ranges
        from the main track and compacts the timeline.
        """
        video_track = self.get_main_video_track()
        if not video_track:
            return 0

        segments = video_track.get("segments", [])
        if not segments:
            return 0

        cuts_count = len(silence_ranges_seconds)
        # CapCut uses microseconds (1 sec = 1,000,000 micros)
        silence_micros = [(int(s * 1_000_000), int(e * 1_000_000)) for s, e in silence_ranges_seconds]
        
        new_segments = []
        timeline_cursor = 0

        for seg in segments:
            tr = seg.get("target_timerange", {})
            seg_start = tr.get("start", 0)
            seg_dur = tr.get("duration", 0)
            seg_end = seg_start + seg_dur
            src_start = seg.get("source_timerange", {}).get("start", 0)

            # Find active intervals inside this segment
            # Start with full segment
            intervals = [(seg_start, seg_end, src_start)]
            
            for sil_start, sil_end in silence_micros:
                next_intervals = []
                for istart, iend, isrc in intervals:
                    if sil_end <= istart or sil_start >= iend:
                        # No overlap
                        next_intervals.append((istart, iend, isrc))
                    else:
                        # Overlap occurs
                        if sil_start > istart:
                            # Keep left piece
                            dur_left = sil_start - istart
                            next_intervals.append((istart, sil_start, isrc))
                        if sil_end < iend:
                            # Keep right piece
                            offset = sil_end - istart
                            next_intervals.append((sil_end, iend, isrc + offset))
                intervals = next_intervals

            for istart, iend, isrc in intervals:
                piece_dur = iend - istart
                if piece_dur > 100_000: # at least 100ms
                    piece = json.loads(json.dumps(seg))
                    piece["id"] = str(uuid.uuid4()).upper()
                    piece["target_timerange"]["start"] = timeline_cursor
                    piece["target_timerange"]["duration"] = piece_dur
                    piece["source_timerange"]["start"] = isrc
                    piece["source_timerange"]["duration"] = piece_dur
                    new_segments.append(piece)
                    timeline_cursor += piece_dur

        video_track["segments"] = new_segments
        self.data["duration"] = timeline_cursor
        self.save()
        return cuts_count


def main():
    parser = argparse.ArgumentParser(description="CapCut Desktop JSON Project Editor")
    subparsers = parser.add_subparsers(dest="command")

    # list
    subparsers.add_parser("list", help="List all CapCut Desktop projects")

    # punch-in
    punch = subparsers.add_parser("punch-in", help="Apply alternating punch-in zoom")
    punch.add_argument("--project", required=True, help="Project name or path")
    punch.add_argument("--scale", type=float, default=1.15, help="Zoom scale factor (default 1.15)")
    punch.add_argument("--step", type=int, default=2, help="Every Nth segment (default 2)")

    # info
    info = subparsers.add_parser("info", help="Get project timeline information")
    info.add_argument("--project", required=True, help="Project name or path")

    args = parser.parse_args()

    if args.command == "list":
        projs = list_projects()
        print(f"Found {len(projs)} CapCut projects:")
        for p in projs:
            print(f" - [{p['id']}] {p['name']} -> {p['path']}")
    elif args.command == "punch-in":
        root = find_capcut_project_root()
        path = args.project
        if not os.path.exists(path) and root:
            path = str(root / args.project)
        draft = CapCutDraft(path)
        count = draft.apply_punch_in_zooms(zoom_scale=args.scale, step=args.step)
        print(f"Applied punch-in zoom (scale {args.scale}) to {count} segments in CapCut project {args.project}.")
    elif args.command == "info":
        root = find_capcut_project_root()
        path = args.project
        if not os.path.exists(path) and root:
            path = str(root / args.project)
        draft = CapCutDraft(path)
        tracks = draft.get_tracks()
        main_v = draft.get_main_video_track()
        segs = len(main_v.get("segments", [])) if main_v else 0
        total_sec = draft.data.get("duration", 0) / 1_000_000
        print(f"Project: {args.project}")
        print(f"Duration: {total_sec:.2f} seconds")
        print(f"Tracks: {len(tracks)}")
        print(f"Main video segments: {segs}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
