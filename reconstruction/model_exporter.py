"""
Model Exporter
==============
Exports the final Blender mesh to GLB format and saves JSON validation reports.

Runs INSIDE Blender (uses bpy).

Author: Body Reconstruction Engine
Version: 0.2.0
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of a GLB export operation."""
    success: bool
    output_path: str
    file_size_bytes: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "file_size_bytes": self.file_size_bytes,
            "error": self.error,
        }


class ModelExporter:
    """
    Exports a Blender mesh object to standard glTF Binary (.glb).
    """

    def export(
        self,
        obj,
        output_path: str | Path,
        apply_modifiers: bool = True,
    ) -> ExportResult:
        import bpy

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            bpy.ops.object.select_all(action="DESELECT")
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

            # Standard Blender 5.2.3 glTF 2.0 parameters
            bpy.ops.export_scene.gltf(
                filepath=str(output_path),
                export_format="GLB",
                use_selection=True,
                export_apply=apply_modifiers,
                export_yup=True,
                export_materials="EXPORT",
                export_texcoords=True,
                export_normals=True,
                export_morph=False,
                export_animations=False,
                export_skins=False,
            )

            if not output_path.exists():
                return ExportResult(
                    success=False,
                    output_path=str(output_path),
                    file_size_bytes=0,
                    error="GLB file was not created",
                )

            size = output_path.stat().st_size
            if size < 5000:
                return ExportResult(
                    success=False,
                    output_path=str(output_path),
                    file_size_bytes=size,
                    error=f"Exported file is too small ({size} bytes)",
                )

            logger.info(f"GLB export successful: {output_path} ({size:,} bytes)")
            return ExportResult(
                success=True,
                output_path=str(output_path),
                file_size_bytes=size,
            )

        except Exception as e:
            logger.error(f"GLB export failed: {e}")
            return ExportResult(
                success=False,
                output_path=str(output_path),
                file_size_bytes=0,
                error=str(e),
            )

    def save_validation_report(
        self,
        report_dict: dict,
        output_path: str | Path,
    ) -> bool:
        output_path = Path(output_path)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2)
            logger.info(f"Validation report saved: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save validation report: {e}")
            return False
