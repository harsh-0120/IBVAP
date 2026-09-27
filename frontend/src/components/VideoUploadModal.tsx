import React, { useState, useRef, useEffect, DragEvent, ChangeEvent } from 'react';
import {
  Upload,
  X,
  FileVideo,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Film,
  Sliders,
} from 'lucide-react';
import { api } from '../services/api';
import { VideoUploadResponse } from '../types/api';

interface VideoUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (uploadedCamera: VideoUploadResponse) => void;
}

const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB
const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.webm'];

export const VideoUploadModal: React.FC<VideoUploadModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [cameraName, setCameraName] = useState<string>('');
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VideoUploadResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset state when modal opens or closes
  useEffect(() => {
    if (isOpen) {
      setFile(null);
      setCameraName('');
      setIsDragging(false);
      setUploading(false);
      setProgress(0);
      setStatusMessage('');
      setError(null);
      setResult(null);
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !uploading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, uploading, onClose]);

  if (!isOpen) return null;

  const validateFile = (selectedFile: File): string | null => {
    if (!selectedFile) {
      return 'No file selected.';
    }

    if (selectedFile.size === 0) {
      return 'The selected file is empty (0 bytes). Please select a valid video recording.';
    }

    if (selectedFile.size > MAX_FILE_SIZE_BYTES) {
      const sizeMB = (selectedFile.size / (1024 * 1024)).toFixed(1);
      return `File size (${sizeMB} MB) exceeds maximum allowed limit of 500 MB.`;
    }

    const lowerName = selectedFile.name.toLowerCase();
    const hasValidExt = ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasValidExt) {
      return `Unsupported file format. Accepted formats: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }

    return null;
  };

  const handleFileSelection = (selectedFile: File) => {
    const validationError = validateFile(selectedFile);
    if (validationError) {
      setError(validationError);
      setFile(null);
      return;
    }

    setError(null);
    setFile(selectedFile);
    setResult(null);

    // Default camera name from filename if not already edited
    if (!cameraName) {
      const baseName = selectedFile.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
      setCameraName(baseName.charAt(0).toUpperCase() + baseName.slice(1));
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!uploading) setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (uploading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelection(e.target.files[0]);
    }
  };

  const handleStartUpload = async () => {
    if (!file) {
      setError('Please select a video file to upload.');
      return;
    }

    const valError = validateFile(file);
    if (valError) {
      setError(valError);
      return;
    }

    setError(null);
    setUploading(true);
    setProgress(0);
    setStatusMessage('Streaming video footage to storage in chunks...');

    try {
      const uploadRes = await api.uploadVideo(
        file,
        cameraName.trim() || undefined,
        (percent: number) => {
          setProgress(percent);
          if (percent >= 100) {
            setStatusMessage('Verifying video signature & calibrating spatial boundaries...');
          } else {
            setStatusMessage(`Uploading footage: ${percent}%`);
          }
        }
      );

      setResult(uploadRes);
      setUploading(false);
      setProgress(100);
      setStatusMessage('Ingestion complete. Pipeline initialized.');
    } catch (err: unknown) {
      setUploading(false);
      setError(err instanceof Error ? err.message : 'Video upload and verification failed.');
    }
  };

  const handleLaunchPipeline = () => {
    if (result) {
      onSuccess(result);
      onClose();
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !uploading) {
          onClose();
        }
      }}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(5, 8, 15, 0.85)',
        backdropFilter: 'blur(4px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        className="modal-container"
        style={{
          background: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-md)',
          width: '100%',
          maxWidth: '560px',
          boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          className="modal-header"
          style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--bg-surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Film size={16} style={{ color: 'var(--accent-cyan)' }} />
            <div>
              <h2
                id="upload-modal-title"
                className="mono"
                style={{
                  fontSize: '13px',
                  fontWeight: 700,
                  letterSpacing: '0.05em',
                  color: 'var(--text-primary)',
                  margin: 0,
                  textTransform: 'uppercase',
                }}
              >
                INGEST RECORDED FOOTAGE
              </h2>
              <p
                style={{
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  margin: '2px 0 0 0',
                }}
              >
                Stream video into YOLO11n + ByteTrack AI surveillance pipeline
              </p>
            </div>
          </div>

          <button
            type="button"
            className="camera-btn"
            onClick={onClose}
            disabled={uploading}
            aria-label="Close dialog"
            style={{
              padding: '4px',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-muted)',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Success Banner if Finished */}
          {result ? (
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: 'var(--radius-sm)',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <CheckCircle2 size={22} style={{ color: 'var(--status-online)', flexShrink: 0 }} />
                <div>
                  <div className="mono" style={{ fontWeight: 700, color: 'var(--status-online)', fontSize: '13px' }}>
                    FOOTAGE INGESTION SUCCESSFUL
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Registered as active surveillance node <strong className="mono" style={{ color: '#fff' }}>{result.camera_id}</strong>
                  </div>
                </div>
              </div>

              {/* Metadata Probed Specs Card */}
              <div
                className="mono"
                style={{
                  background: 'var(--bg-root)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  padding: '10px 12px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: '8px',
                  fontSize: '11px',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>CAMERA ID: </span>
                  <strong style={{ color: 'var(--accent-cyan)' }}>{result.camera_id}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>NAME: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{result.name}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>RESOLUTION: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{result.resolution}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>FRAMERATE: </span>
                  <strong style={{ color: 'var(--status-online)' }}>{result.source_fps} FPS</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>DURATION: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{result.duration_sec.toFixed(1)}s</strong>
                  <span style={{ color: 'var(--text-dim)', fontSize: '10px' }}> ({result.frame_count} frames)</span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>SIZE: </span>
                  <strong style={{ color: 'var(--text-primary)' }}>{formatFileSize(result.file_size_bytes)}</strong>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                Spatial boundaries calibrated and ready for real-time intrusion and tripwire analysis.
              </div>
            </div>
          ) : (
            <>
              {/* Drag and Drop Zone */}
              <div
                className={`file-dropzone ${isDragging ? 'dragging' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !uploading && fileInputRef.current?.click()}
                style={{
                  border: `2px dashed ${
                    isDragging ? 'var(--accent-cyan)' : file ? 'var(--status-online)' : 'var(--border-medium)'
                  }`,
                  backgroundColor: isDragging
                    ? 'var(--accent-cyan-dim)'
                    : file
                    ? 'rgba(16, 185, 129, 0.04)'
                    : 'var(--bg-surface)',
                  borderRadius: 'var(--radius-md)',
                  padding: '24px 16px',
                  textAlign: 'center',
                  cursor: uploading ? 'not-allowed' : 'pointer',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".mp4,.avi,.mov,.mkv,.webm,video/mp4,video/x-msvideo,video/quicktime,video/x-matroska,video/webm"
                  onChange={handleFileInputChange}
                  style={{ display: 'none' }}
                  disabled={uploading}
                />

                {file ? (
                  <>
                    <FileVideo size={36} style={{ color: 'var(--status-online)' }} />
                    <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                      {file.name}
                    </div>
                    <div className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {formatFileSize(file.size)} • Click to replace file
                    </div>
                  </>
                ) : (
                  <>
                    <Upload size={32} style={{ color: 'var(--accent-cyan)' }} />
                    <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                      {isDragging ? 'DROP SURVEILLANCE VIDEO HERE' : 'CHOOSE OR DRAG VIDEO FOOTAGE'}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      Supports MP4, AVI, MOV, MKV, WebM up to 500 MB
                    </div>
                  </>
                )}

                {/* Format Badges */}
                <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                  {['MP4', 'AVI', 'MOV', 'MKV', 'WEBM'].map((fmt) => (
                    <span
                      key={fmt}
                      className="mono"
                      style={{
                        fontSize: '9px',
                        background: 'var(--bg-root)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '2px',
                        padding: '1px 5px',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {fmt}
                    </span>
                  ))}
                  <span
                    className="mono"
                    style={{
                      fontSize: '9px',
                      background: 'var(--bg-root)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '2px',
                      padding: '1px 5px',
                      color: 'var(--accent-cyan)',
                    }}
                  >
                    MAX 500MB
                  </span>
                </div>
              </div>

              {/* Camera Source Label Input */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label
                  htmlFor="camera-name-input"
                  className="mono"
                  style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Sliders size={12} style={{ color: 'var(--accent-cyan)' }} />
                  SURVEILLANCE NODE LABEL (OPTIONAL)
                </label>
                <input
                  id="camera-name-input"
                  type="text"
                  value={cameraName}
                  onChange={(e) => setCameraName(e.target.value)}
                  placeholder="e.g., Perimeter Sector B Patrol Cam"
                  disabled={uploading}
                  className="mono"
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    color: 'var(--text-primary)',
                    fontSize: '12px',
                    outline: 'none',
                  }}
                />
              </div>

              {/* Upload Progress Bar */}
              {uploading && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                    <span className="mono" style={{ color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <RefreshCw size={12} className="spin-animate" />
                      {statusMessage}
                    </span>
                    <span className="mono" style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                      {progress}%
                    </span>
                  </div>

                  <div
                    style={{
                      height: '6px',
                      background: 'var(--bg-surface)',
                      borderRadius: '3px',
                      overflow: 'hidden',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${progress}%`,
                        background: 'linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))',
                        transition: 'width 0.2s ease',
                      }}
                    />
                  </div>
                </div>
              )}
            </>
          )}

          {/* Error Banner */}
          {error && (
            <div
              style={{
                background: 'var(--severity-critical-bg)',
                border: '1px solid var(--severity-critical-border)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: 'var(--severity-critical)',
                fontSize: '11px',
              }}
              role="alert"
            >
              <AlertTriangle size={16} style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>{error}</div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          className="modal-footer"
          style={{
            padding: '12px 18px',
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-surface)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '8px',
          }}
        >
          {result ? (
            <button
              type="button"
              className="camera-btn mono active"
              onClick={handleLaunchPipeline}
              style={{
                padding: '8px 16px',
                fontSize: '11px',
                background: 'var(--status-online)',
                borderColor: 'var(--status-online)',
                color: '#fff',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <CheckCircle2 size={14} />
              <span>LAUNCH LIVE PIPELINE & MONITOR</span>
            </button>
          ) : (
            <>
              <button
                type="button"
                className="camera-btn mono"
                onClick={onClose}
                disabled={uploading}
                style={{ padding: '6px 14px', fontSize: '11px' }}
              >
                CANCEL
              </button>
              <button
                type="button"
                className="camera-btn mono active"
                onClick={handleStartUpload}
                disabled={!file || uploading}
                style={{
                  padding: '6px 16px',
                  fontSize: '11px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  opacity: !file || uploading ? 0.5 : 1,
                  cursor: !file || uploading ? 'not-allowed' : 'pointer',
                }}
              >
                <Upload size={13} />
                <span>{uploading ? 'INGESTING...' : 'UPLOAD & ANALYZE'}</span>
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
