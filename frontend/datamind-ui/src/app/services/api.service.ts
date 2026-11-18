import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface HealthResponse {
  status: string;
  message: string;
}

export interface AskResponse {
  success: boolean;
  dataset_id?: number;
  question: string;
  sql: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  truncated: boolean;
}

export interface Dataset {
  dataset_id: number;
  name: string;
  original_filename: string;
  schema_name: string;
  status: 'processing' | 'ready' | 'failed';
  table_count: number;
  row_count: number;
  is_builtin: boolean;
  error_message: string | null;
  created_at: string;
}

export interface DatasetListResponse {
  success: boolean;
  total: number;
  items: Dataset[];
}

export interface DatasetUploadResponse extends Dataset {
  success: boolean;
  tables: string[];
}

export interface DatasetColumn {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
}

export interface DatasetTable {
  name: string;
  columns: DatasetColumn[];
  primary_key: string[];
  foreign_keys: {
    columns: string[];
    referenced_schema: string | null;
    referenced_table: string | null;
    referenced_columns: string[];
  }[];
}

export interface DatasetSchema {
  success: boolean;
  schema_name: string;
  table_count: number;
  tables: DatasetTable[];
}

export interface HistoryItem {
  history_id: number;
  question: string;
  generated_sql: string;
  row_count: number;
  truncated: boolean;
  result_columns: string[];
  result_rows: (string | number | boolean | null)[][];
  created_at: string;
}

export interface HistoryResponse {
  success: boolean;
  total: number;
  items: HistoryItem[];
}

export interface GuestClaimResponse {
  success: boolean;
  message: string;
  transferred_count: number;
  dataset_ids: number[];
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  private http = inject(HttpClient);

  private apiUrl = '';

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(
      `${this.apiUrl}/api/health`
    );
  }

  ask(question: string): Observable<AskResponse> {
    return this.http.post<AskResponse>(
      `${this.apiUrl}/api/ask`,
      { question }
    );
  }

  getDatasets(): Observable<DatasetListResponse> {
    return this.http.get<DatasetListResponse>(
      `${this.apiUrl}/api/datasets`,
    );
  }

  uploadDataset(name: string, file: File): Observable<DatasetUploadResponse> {
    const formData = new FormData();
    formData.append('name', name);
    formData.append('file', file);

    return this.http.post<DatasetUploadResponse>(
      `${this.apiUrl}/api/datasets/upload`,
      formData,
    );
  }

  getDatasetSchema(datasetId: number): Observable<DatasetSchema> {
    return this.http.get<DatasetSchema>(
      `${this.apiUrl}/api/datasets/${datasetId}/schema`,
    );
  }

  askDataset(datasetId: number, question: string): Observable<AskResponse> {
    return this.http.post<AskResponse>(
      `${this.apiUrl}/api/datasets/${datasetId}/ask`,
      { question },
    );
  }

  getDatasetHistory(datasetId: number, limit = 20): Observable<HistoryResponse> {
    return this.http.get<HistoryResponse>(
      `${this.apiUrl}/api/datasets/${datasetId}/history?limit=${limit}`,
    );
  }

  deleteDataset(datasetId: number): Observable<{ success: boolean; message: string; dataset_id: number }> {
    return this.http.delete<{ success: boolean; message: string; dataset_id: number }>(
      `${this.apiUrl}/api/datasets/${datasetId}`,
    );
  }

  getHistory(limit = 20): Observable<HistoryResponse> {
    return this.http.get<HistoryResponse>(
      `${this.apiUrl}/api/history?limit=${limit}`,
    );
  }

  claimGuestDatasets(guestToken: string): Observable<GuestClaimResponse> {
    return this.http.post<GuestClaimResponse>(
      `${this.apiUrl}/api/datasets/claim-guest`,
      { guest_token: guestToken },
    );
  }
}