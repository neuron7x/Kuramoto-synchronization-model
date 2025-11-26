# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""S3 storage backend for market feed recordings.

Provides upload/download capabilities for market feed recordings with
versioning, checksums, and metadata preservation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from core.data.market_feed import MarketFeedMetadata, MarketFeedRecording


class MarketFeedStorage:
    """S3 storage backend for market feed recordings."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "market-feeds",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        """Initialize S3 storage backend.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for recordings
            region: AWS region (defaults to environment config)
            endpoint_url: Custom S3 endpoint (for testing with LocalStack, MinIO, etc.)
        """
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self.endpoint_url = endpoint_url

        # Lazy import boto3 to keep it as optional dependency
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for S3 storage. "
                    "Install with: pip install boto3"
                ) from e

            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
            )

        return self._s3_client

    def _generate_key(self, recording_name: str, extension: str = ".jsonl") -> str:
        """Generate S3 key for recording."""
        return f"{self.prefix}/{recording_name}{extension}"

    def _calculate_checksum(self, data: bytes) -> str:
        """Calculate SHA256 checksum."""
        return hashlib.sha256(data).hexdigest()

    def upload_recording(
        self,
        recording: MarketFeedRecording,
        recording_name: str,
        include_metadata: bool = True,
    ) -> dict[str, str]:
        """Upload recording to S3.

        Args:
            recording: MarketFeedRecording to upload
            recording_name: Name for the recording (without extension)
            include_metadata: Whether to upload metadata file

        Returns:
            Dictionary with upload info (keys, checksums, URIs)
        """
        # Serialize recording to JSONL
        jsonl_lines = [record.to_jsonl() for record in recording.records]
        jsonl_data = "\n".join(jsonl_lines).encode("utf-8")
        jsonl_checksum = self._calculate_checksum(jsonl_data)

        # Upload JSONL file
        jsonl_key = self._generate_key(recording_name, ".jsonl")
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=jsonl_key,
            Body=jsonl_data,
            ContentType="application/x-ndjson",
            Metadata={
                "checksum": jsonl_checksum,
                "record_count": str(len(recording)),
            },
        )

        result = {
            "jsonl_key": jsonl_key,
            "jsonl_checksum": jsonl_checksum,
            "jsonl_uri": f"s3://{self.bucket}/{jsonl_key}",
        }

        # Upload metadata if requested
        if include_metadata and recording.metadata:
            metadata_json = json.dumps(
                recording.metadata.to_dict(),
                indent=2,
            ).encode("utf-8")
            metadata_checksum = self._calculate_checksum(metadata_json)

            metadata_key = self._generate_key(recording_name, ".metadata.json")
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=metadata_key,
                Body=metadata_json,
                ContentType="application/json",
                Metadata={
                    "checksum": metadata_checksum,
                },
            )

            result.update(
                {
                    "metadata_key": metadata_key,
                    "metadata_checksum": metadata_checksum,
                    "metadata_uri": f"s3://{self.bucket}/{metadata_key}",
                }
            )

        return result

    def download_recording(
        self,
        recording_name: str,
        include_metadata: bool = True,
        verify_checksum: bool = True,
    ) -> MarketFeedRecording:
        """Download recording from S3.

        Args:
            recording_name: Name of the recording (without extension)
            include_metadata: Whether to download metadata file
            verify_checksum: Whether to verify checksums

        Returns:
            MarketFeedRecording
        """
        # Download JSONL file
        jsonl_key = self._generate_key(recording_name, ".jsonl")
        response = self.s3_client.get_object(Bucket=self.bucket, Key=jsonl_key)
        jsonl_data = response["Body"].read()

        # Verify checksum if requested
        if verify_checksum:
            stored_checksum = response.get("Metadata", {}).get("checksum")
            if stored_checksum:
                actual_checksum = self._calculate_checksum(jsonl_data)
                if actual_checksum != stored_checksum:
                    raise ValueError(
                        f"Checksum mismatch for {jsonl_key}: "
                        f"expected {stored_checksum}, got {actual_checksum}"
                    )

        # Parse JSONL
        from core.data.market_feed import MarketFeedRecord

        records = []
        for line in jsonl_data.decode("utf-8").splitlines():
            if line.strip():
                records.append(MarketFeedRecord.from_jsonl(line))

        recording = MarketFeedRecording(records)

        # Download metadata if requested
        if include_metadata:
            try:
                metadata_key = self._generate_key(recording_name, ".metadata.json")
                response = self.s3_client.get_object(
                    Bucket=self.bucket, Key=metadata_key
                )
                metadata_json = response["Body"].read()

                if verify_checksum:
                    stored_checksum = response.get("Metadata", {}).get("checksum")
                    if stored_checksum:
                        actual_checksum = self._calculate_checksum(metadata_json)
                        if actual_checksum != stored_checksum:
                            raise ValueError(
                                f"Checksum mismatch for {metadata_key}: "
                                f"expected {stored_checksum}, got {actual_checksum}"
                            )

                metadata_dict = json.loads(metadata_json)
                recording.metadata = MarketFeedMetadata.from_dict(metadata_dict)
            except self.s3_client.exceptions.NoSuchKey:
                # Metadata file doesn't exist, continue without it
                pass

        return recording

    def list_recordings(self, prefix_filter: Optional[str] = None) -> list[str]:
        """List available recordings in S3.

        Args:
            prefix_filter: Additional prefix filter

        Returns:
            List of recording names (without extensions)
        """
        prefix = self.prefix
        if prefix_filter:
            prefix = f"{self.prefix}/{prefix_filter}"

        paginator = self.s3_client.get_paginator("list_objects_v2")
        recording_names = set()

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".jsonl"):
                    # Extract recording name
                    name = key[len(self.prefix) + 1 : -6]  # Remove prefix and .jsonl
                    recording_names.add(name)

        return sorted(recording_names)

    def delete_recording(
        self,
        recording_name: str,
        delete_metadata: bool = True,
    ) -> None:
        """Delete recording from S3.

        Args:
            recording_name: Name of the recording (without extension)
            delete_metadata: Whether to also delete metadata file
        """
        # Delete JSONL file
        jsonl_key = self._generate_key(recording_name, ".jsonl")
        self.s3_client.delete_object(Bucket=self.bucket, Key=jsonl_key)

        # Delete metadata file if requested
        if delete_metadata:
            metadata_key = self._generate_key(recording_name, ".metadata.json")
            try:
                self.s3_client.delete_object(Bucket=self.bucket, Key=metadata_key)
            except self.s3_client.exceptions.NoSuchKey:
                # Metadata file doesn't exist, ignore
                pass

    def upload_from_file(
        self,
        local_path: Path,
        recording_name: str,
        metadata_path: Optional[Path] = None,
    ) -> dict[str, str]:
        """Upload recording from local file.

        Args:
            local_path: Path to local JSONL file
            recording_name: Name for the recording
            metadata_path: Optional path to metadata file

        Returns:
            Dictionary with upload info
        """
        recording = MarketFeedRecording.read_jsonl(local_path)

        if metadata_path and metadata_path.exists():
            with open(metadata_path, "r") as f:
                metadata_dict = json.load(f)
                recording.metadata = MarketFeedMetadata.from_dict(metadata_dict)

        return self.upload_recording(
            recording,
            recording_name,
            include_metadata=recording.metadata is not None,
        )

    def download_to_file(
        self,
        recording_name: str,
        local_path: Path,
        metadata_path: Optional[Path] = None,
    ) -> None:
        """Download recording to local file.

        Args:
            recording_name: Name of the recording
            local_path: Path for local JSONL file
            metadata_path: Optional path for metadata file
        """
        recording = self.download_recording(recording_name, include_metadata=True)

        recording.write_jsonl(local_path)

        if metadata_path and recording.metadata:
            with open(metadata_path, "w") as f:
                json.dump(recording.metadata.to_dict(), f, indent=2)
