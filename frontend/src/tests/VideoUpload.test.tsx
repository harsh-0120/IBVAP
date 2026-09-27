import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VideoUploadModal } from '../components/VideoUploadModal';
import { api } from '../services/api';
import { VideoUploadResponse } from '../types/api';

describe('VideoUploadModal Component', () => {
  const mockSuccessResponse: VideoUploadResponse = {
    camera_id: 'CAM-UPLOAD-TEST',
    name: 'Sector 4 Patrol',
    file_path: 'data/uploads/sector4.mp4',
    resolution: '1920x1080',
    source_fps: 30.0,
    frame_count: 600,
    duration_sec: 20.0,
    file_size_bytes: 15 * 1024 * 1024,
    message: 'Video uploaded and registered successfully.',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <VideoUploadModal
        isOpen={false}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    expect(screen.queryByText(/INGEST RECORDED FOOTAGE/i)).not.toBeInTheDocument();
  });

  it('renders modal with dragzone and badges when isOpen is true', () => {
    render(
      <VideoUploadModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    expect(screen.getByText(/INGEST RECORDED FOOTAGE/i)).toBeInTheDocument();
    expect(screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i)).toBeInTheDocument();
    expect(screen.getByText('MP4')).toBeInTheDocument();
    expect(screen.getByText('AVI')).toBeInTheDocument();
    expect(screen.getByText('MAX 500MB')).toBeInTheDocument();
  });

  it('rejects unsupported file formats with clear validation error', () => {
    render(
      <VideoUploadModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    const invalidFile = new File(['text content'], 'notes.txt', { type: 'text/plain' });
    const dropzone = screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i).closest('.file-dropzone')!;

    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [invalidFile],
      },
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Unsupported file format/i)).toBeInTheDocument();
  });

  it('rejects empty (0 byte) files with clear error', () => {
    render(
      <VideoUploadModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    const emptyFile = new File([], 'empty.mp4', { type: 'video/mp4' });
    const dropzone = screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i).closest('.file-dropzone')!;

    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [emptyFile],
      },
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/The selected file is empty/i)).toBeInTheDocument();
  });

  it('rejects files exceeding 500 MB', () => {
    render(
      <VideoUploadModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    // Mock a 501 MB file
    const hugeFile = new File([''], 'huge.mp4', { type: 'video/mp4' });
    Object.defineProperty(hugeFile, 'size', { value: 501 * 1024 * 1024 });

    const dropzone = screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i).closest('.file-dropzone')!;

    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [hugeFile],
      },
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/exceeds maximum allowed limit of 500 MB/i)).toBeInTheDocument();
  });

  it('successfully uploads valid video, updates progress, and provides launch action', async () => {
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    vi.spyOn(api, 'uploadVideo').mockImplementation(
      async (_file, _name, onProgress) => {
        if (onProgress) {
          onProgress(50);
          onProgress(100);
        }
        return mockSuccessResponse;
      }
    );

    render(
      <VideoUploadModal
        isOpen={true}
        onClose={handleClose}
        onSuccess={handleSuccess}
      />
    );

    const validFile = new File(['dummy content'], 'patrol_sector.mp4', { type: 'video/mp4' });
    Object.defineProperty(validFile, 'size', { value: 10 * 1024 * 1024 });

    const dropzone = screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i).closest('.file-dropzone')!;
    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [validFile],
      },
    });

    // File name displayed, default camera name set
    expect(screen.getByText('patrol_sector.mp4')).toBeInTheDocument();

    const uploadBtn = screen.getByRole('button', { name: /UPLOAD & ANALYZE/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByText(/FOOTAGE INGESTION SUCCESSFUL/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText('CAM-UPLOAD-TEST').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('1920x1080')).toBeInTheDocument();
    expect(screen.getByText(/30 FPS/i)).toBeInTheDocument();


    // Click launch button
    const launchBtn = screen.getByRole('button', { name: /LAUNCH LIVE PIPELINE & MONITOR/i });
    fireEvent.click(launchBtn);

    expect(handleSuccess).toHaveBeenCalledWith(mockSuccessResponse);
    expect(handleClose).toHaveBeenCalled();
  });

  it('displays error message when upload fails on the backend', async () => {
    vi.spyOn(api, 'uploadVideo').mockRejectedValue(
      new Error('Corrupted or invalid video file: OpenCV could not open container.')
    );

    render(
      <VideoUploadModal
        isOpen={true}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );

    const corruptFile = new File(['junk content'], 'corrupted.mp4', { type: 'video/mp4' });
    Object.defineProperty(corruptFile, 'size', { value: 1024 * 1024 });

    const dropzone = screen.getByText(/CHOOSE OR DRAG VIDEO FOOTAGE/i).closest('.file-dropzone')!;
    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [corruptFile],
      },
    });

    const uploadBtn = screen.getByRole('button', { name: /UPLOAD & ANALYZE/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText(/OpenCV could not open container/i)).toBeInTheDocument();
  });
});
