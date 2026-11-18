import { Component, OnInit, inject, signal, ElementRef, ViewChild } from '@angular/core';

import { DatePipe } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { FormsModule } from '@angular/forms';
import Chart from 'chart.js/auto';

import {
  ApiService,
  AskResponse,
  Dataset,
  DatasetSchema,
  HistoryItem,
} from './services/api.service';
import { AuthService } from './services/auth.service';

type ChartType = 'bar' | 'line' | 'doughnut';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, FormsModule, DatePipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private apiService = inject(ApiService);
  private authService = inject(AuthService);

  @ViewChild('resultChart')
  resultChart?: ElementRef<HTMLCanvasElement>;

  @ViewChild('fileInput')
  fileInput?: ElementRef<HTMLInputElement>;

  private chartInstance: Chart | null = null;

  isConnected = signal(false);
  statusMessage = signal('Verificando conexión...');
  currentUser = this.authService.currentUser;
  isRestoringSession = signal(true);
  authMode = signal<'login' | 'register'>('login');
  authEmail = '';
  authPassword = '';
  authBusy = signal(false);
  authError = signal('');
  authMessage = signal('');
  showAuth = signal(false);
  isGuest = this.authService.isGuest;

  question = '';

  isLoading = signal(false);
  answer = signal<AskResponse | null>(null);
  errorMessage = signal('');
  chartType = signal<ChartType>('bar');
  chartAvailable = signal(false);
  chartMessage = signal('');

  history = signal<HistoryItem[]>([]);
  historyLoading = signal(false);
  historyError = signal('');

  selectedHistory = signal<HistoryItem | null>(null);

  datasets = signal<Dataset[]>([]);
  selectedDataset = signal<Dataset | null>(null);
  datasetsLoading = signal(false);
  datasetsError = signal('');
  schema = signal<DatasetSchema | null>(null);
  schemaLoading = signal(false);
  schemaExpanded = signal(false);
  isUploading = signal(false);
  uploadError = signal('');
  isDragging = signal(false);

  ngOnInit(): void {
    this.authService.restoreSession().subscribe(() => {
      if (this.currentUser() || this.isGuest()) {
        this.initializeDashboard();
      } else {
        this.startGuestSession();
      }
    });
  }

  private initializeDashboard(): void {
    this.isRestoringSession.set(false);
    this.checkConnection();
    this.loadDatasets();
  }

  startGuestSession(): void {
    this.isRestoringSession.set(true);

    this.authService.startGuestSession().subscribe({
      next: () => {
        this.initializeDashboard();
      },
      error: (error) => {
        console.error('Error al iniciar sesión de invitado:', error);
        this.isRestoringSession.set(false);
        this.isConnected.set(false);
        this.statusMessage.set('No se pudo iniciar la sesión de invitado');
        this.datasetsError.set('No fue posible iniciar una sesión temporal. Recarga la página.');
      },
    });
  }

  openAuth(mode: 'login' | 'register' = 'login'): void {
    this.authMode.set(mode);
    this.authError.set('');
    this.authMessage.set('');
    this.showAuth.set(true);
  }

  closeAuth(): void {
    this.showAuth.set(false);
    this.authPassword = '';
    this.authError.set('');
    this.authMessage.set('');
  }

  submitAuth(): void {
    const email = this.authEmail.trim();
    const password = this.authPassword;

    if (!email || password.length < 8 || this.authBusy()) {
      this.authError.set('Introduce un correo y una contraseña de al menos 8 caracteres.');
      return;
    }

    this.authBusy.set(true);
    this.authError.set('');
    this.authMessage.set('');

    if (this.authMode() === 'login') {
      this.authService.login(email, password).subscribe({
        next: () => {
          this.authBusy.set(false);
          this.authPassword = '';
          this.checkConnection();

          const guestToken = this.authService.getGuestToken();

          if (!guestToken) {
            this.showAuth.set(false);
            this.loadDatasets();
            return;
          }

          this.apiService.claimGuestDatasets(guestToken).subscribe({
            next: (response) => {
              console.log('Datasets transferidos:', response.transferred_count);
              this.authService.clearGuestToken();
              this.showAuth.set(false);
              this.datasetsError.set('');
              this.loadDatasets();
            },
            error: (claimError: { error?: { detail?: string } }) => {
              console.error('Error al transferir datasets:', claimError);
              this.showAuth.set(false);
              this.loadDatasets();
              this.datasetsError.set(
                'Iniciaste sesión, pero no se pudieron transferir tus datasets temporales. ' +
                  (claimError.error?.detail || 'Inténtalo nuevamente.'),
              );
            },
          });
        },
        error: (error: { error?: { detail?: string } }) => {
          this.authBusy.set(false);
          this.authError.set(error.error?.detail || 'No se pudo iniciar sesión.');
        },
      });
      return;
    }

    this.authService.register(email, password).subscribe({
      next: (response) => {
        this.authBusy.set(false);
        this.authPassword = '';
        this.authMode.set('login');
        this.authMessage.set(response.message);
      },
      error: (error: { error?: { detail?: string } }) => {
        this.authBusy.set(false);
        this.authError.set(error.error?.detail || 'No se pudo crear la cuenta.');
      },
    });
  }

  switchAuthMode(): void {
    this.authMode.update((mode) => (mode === 'login' ? 'register' : 'login'));
    this.authError.set('');
    this.authMessage.set('');
  }

  logout(): void {
    this.authService.logout();

    this.datasets.set([]);
    this.selectedDataset.set(null);
    this.schema.set(null);
    this.history.set([]);
    this.answer.set(null);
    this.selectedHistory.set(null);
    this.showAuth.set(false);

    this.startGuestSession();
  }
  checkConnection(): void {
    this.apiService.getHealth().subscribe({
      next: (response) => {
        this.isConnected.set(response.status === 'ok');
        this.statusMessage.set(response.message);
      },
      error: () => {
        this.isConnected.set(false);
        this.statusMessage.set('Backend desconectado');
      },
    });
  }

  submitQuery(): void {
    const userQuestion = this.question.trim();

    if (!userQuestion || this.isLoading() || !this.isConnected()) {
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');
    this.answer.set(null);
    this.selectedHistory.set(null);

    this.chartInstance?.destroy();
    this.chartInstance = null;

    const request = this.selectedDataset()
      ? this.apiService.askDataset(this.selectedDataset()!.dataset_id, userQuestion)
      : this.apiService.ask(userQuestion);

    request.subscribe({
      next: (response) => {
        this.answer.set({
          ...response,
          question: response.question || userQuestion,
          dataset_id: this.selectedDataset()?.dataset_id ?? response.dataset_id,
        });
        this.isLoading.set(false);
        this.loadHistory();

        // Esperar a que Angular renderice el canvas.
        setTimeout(() => this.renderChart(response), 0);
      },

      error: (error) => {
        console.error(error);

        this.errorMessage.set(error.error?.detail || 'No se pudo procesar la consulta.');

        this.isLoading.set(false);
      },
    });
  }

  changeChartType(value: string): void {
    const allowedTypes: ChartType[] = ['bar', 'line', 'doughnut'];

    if (!allowedTypes.includes(value as ChartType)) {
      return;
    }

    this.chartType.set(value as ChartType);

    const currentAnswer = this.answer();

    if (currentAnswer) {
      setTimeout(() => this.renderChart(currentAnswer), 0);
    }
  }

  private renderChartLegacy(response: AskResponse): void {
    const canvas = this.resultChart?.nativeElement;

    if (!canvas || !response.rows.length) {
      return;
    }

    // Buscar una columna descriptiva.
    const labelKeywords = /name|category|city|month|period|date|order_number|sku/i;

    let labelIndex = response.columns.findIndex(
      (column, index) =>
        labelKeywords.test(column) && response.rows.some((row) => typeof row[index] === 'string'),
    );

    if (labelIndex === -1) {
      labelIndex = response.columns.findIndex((_, index) =>
        response.rows.some((row) => typeof row[index] === 'string'),
      );
    }

    // Buscar una columna numérica que represente una métrica.
    const metricKeywords =
      /total|sales|amount|revenue|units|quantity|count|price|stock|profit|average/i;

    let valueIndex = response.columns.findIndex(
      (column, index) =>
        index !== labelIndex &&
        metricKeywords.test(column) &&
        response.rows.some((row) => typeof row[index] === 'number'),
    );

    // Si no se identifica una métrica, utilizar la última numérica.
    if (valueIndex === -1) {
      for (let index = response.columns.length - 1; index >= 0; index--) {
        if (index !== labelIndex && response.rows.some((row) => typeof row[index] === 'number')) {
          valueIndex = index;
          break;
        }
      }
    }

    if (labelIndex === -1 || valueIndex === -1) {
      this.chartInstance?.destroy();
      this.chartInstance = null;
      return;
    }

    const labels = response.rows.map((row) => String(row[labelIndex]));

    const values = response.rows.map((row) => Number(row[valueIndex]) || 0);

    const selectedType = this.chartType();

    const palette = ['#6255df', '#897de9', '#a99ff0', '#c4bdf5', '#dedafb', '#5144c7'];

    const colors = labels.map((_, index) => palette[index % palette.length]);

    this.chartInstance?.destroy();

    this.chartInstance = new Chart(canvas, {
      type: selectedType,

      data: {
        labels,

        datasets: [
          {
            label: response.columns[valueIndex].replaceAll('_', ' '),

            data: values,

            backgroundColor: selectedType === 'doughnut' ? colors : '#7569e8',

            borderColor: '#6255df',

            borderWidth: selectedType === 'line' ? 3 : 0,

            borderRadius: selectedType === 'bar' ? 6 : 0,

            maxBarThickness: 32,

            tension: 0.3,

            fill: false,
          },
        ],
      },

      options: {
        responsive: true,
        maintainAspectRatio: false,

        indexAxis: selectedType === 'bar' ? 'y' : 'x',

        plugins: {
          legend: {
            display: selectedType === 'doughnut',
            position: 'top',
          },
        },

        scales:
          selectedType === 'doughnut'
            ? {}
            : {
                x: {
                  beginAtZero: true,
                  ticks: {
                    precision: 0,
                  },
                },

                y: {
                  grid: {
                    display: false,
                  },
                },
              },
      },
    });
  }

  renderChart(response: AskResponse): void {
    this.chartInstance?.destroy();
    this.chartInstance = null;
    this.chartAvailable.set(false);
    this.chartMessage.set('');

    if (!response.rows || response.rows.length === 0) {
      this.chartMessage.set('No hay resultados disponibles para generar una visualización.');
      return;
    }

    const labelKeywords = /name|category|city|month|period|date|order_number|sku/i;
    let labelIndex = response.columns.findIndex(
      (column, index) =>
        labelKeywords.test(column) && response.rows.some((row) => typeof row[index] === 'string'),
    );

    if (labelIndex === -1) {
      labelIndex = response.columns.findIndex((_, index) =>
        response.rows.some((row) => typeof row[index] === 'string'),
      );
    }

    const metricKeywords =
      /total|sales|amount|revenue|units|quantity|count|price|stock|profit|average/i;
    let valueIndex = response.columns.findIndex(
      (column, index) =>
        index !== labelIndex &&
        metricKeywords.test(column) &&
        response.rows.some((row) => typeof row[index] === 'number'),
    );

    if (valueIndex === -1) {
      for (let index = response.columns.length - 1; index >= 0; index--) {
        if (index !== labelIndex && response.rows.some((row) => typeof row[index] === 'number')) {
          valueIndex = index;
          break;
        }
      }
    }

    if (labelIndex === -1 || valueIndex === -1) {
      this.chartMessage.set(
        'No es posible generar un gráfico con estos resultados. Se necesita una columna de categorías y otra con valores numéricos. Puedes consultar el resultado en la tabla.',
      );
      return;
    }

    const labels = response.rows.map((row) => String(row[labelIndex]));
    const values = response.rows.map((row) => Number(row[valueIndex]));

    if (!values.every(Number.isFinite)) {
      this.chartMessage.set(
        'Los datos obtenidos no tienen un formato numérico adecuado para generar el gráfico.',
      );
      return;
    }

    const canvas = this.resultChart?.nativeElement;
    if (!canvas) {
      this.chartMessage.set('No se pudo preparar el espacio de visualización.');
      return;
    }

    this.chartAvailable.set(true);
    const selectedType = this.chartType();
    const palette = ['#6255df', '#897de9', '#a99ff0', '#c4bdf5', '#dedafb', '#5144c7'];
    const colors = labels.map((_, index) => palette[index % palette.length]);

    this.chartInstance = new Chart(canvas, {
      type: selectedType,
      data: {
        labels,
        datasets: [
          {
            label: response.columns[valueIndex].replaceAll('_', ' '),
            data: values,
            backgroundColor: selectedType === 'doughnut' ? colors : '#7569e8',
            borderColor: '#6255df',
            borderWidth: selectedType === 'line' ? 3 : 0,
            borderRadius: selectedType === 'bar' ? 6 : 0,
            maxBarThickness: 32,
            tension: 0.3,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: selectedType === 'bar' ? 'y' : 'x',
        plugins: {
          legend: { display: selectedType === 'doughnut', position: 'top' },
        },
        scales:
          selectedType === 'doughnut'
            ? {}
            : {
                x: { beginAtZero: true, ticks: { precision: 0 } },
                y: { grid: { display: false } },
              },
      },
    });
  }

  exportCsv(): void {
    const result = this.answer();

    if (!result || !result.rows.length) {
      return;
    }

    // Escapar valores para el formato CSV.
    const escapeCsv = (value: unknown): string => {
      const text = value === null || value === undefined ? '' : String(value);

      return `"${text.replace(/"/g, '""')}"`;
    };

    // Crear encabezados y filas.
    const headers = result.columns.map(escapeCsv).join(',');

    const rows = result.rows.map((row) => row.map(escapeCsv).join(','));

    // BOM para facilitar la lectura de caracteres especiales en Excel.
    const csvContent = '\uFEFF' + [headers, ...rows].join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = `datamind-resultados-${new Date().toISOString().slice(0, 10)}.csv`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  }

  clearResults(): void {
    this.chartInstance?.destroy();
    this.chartInstance = null;

    this.answer.set(null);
    this.errorMessage.set('');
    this.question = '';
    this.selectedHistory.set(null);
  }

  loadDatasets(selectDatasetId?: number): void {
    this.datasetsLoading.set(true);
    this.datasetsError.set('');

    this.apiService.getDatasets().subscribe({
      next: (response) => {
        this.datasets.set(response.items);
        this.datasetsLoading.set(false);

        const selected =
          response.items.find(
            (dataset) =>
              dataset.dataset_id === (selectDatasetId ?? this.selectedDataset()?.dataset_id),
          ) ?? response.items.find((dataset) => dataset.status === 'ready');

        if (selected) {
          this.selectDataset(selected);
        } else {
          this.selectedDataset.set(null);
          this.schema.set(null);
          this.history.set([]);
        }
      },
      error: (error) => {
        console.error('Error al cargar datasets:', error);
        this.datasetsLoading.set(false);
        this.datasetsError.set(error.error?.detail || 'No se pudieron cargar los datasets.');
      },
    });
  }

  selectDataset(dataset: Dataset): void {
    if (dataset.status !== 'ready') {
      return;
    }

    this.selectedDataset.set(dataset);
    this.selectedHistory.set(null);
    this.answer.set(null);
    this.loadSchema();
    this.loadHistory();
  }

  selectDatasetById(value: string | number): void {
    const dataset = this.datasets().find((item) => item.dataset_id === Number(value));
    if (dataset) {
      this.selectDataset(dataset);
    }
  }

  toggleSchema(): void {
    this.schemaExpanded.update((expanded) => !expanded);
  }

  loadSchema(): void {
    const dataset = this.selectedDataset();
    if (!dataset) {
      return;
    }

    this.schemaLoading.set(true);
    this.apiService.getDatasetSchema(dataset.dataset_id).subscribe({
      next: (response) => {
        this.schema.set(response);
        this.schemaLoading.set(false);
      },
      error: (error) => {
        console.error('Error al cargar esquema:', error);
        this.schemaLoading.set(false);
        this.schema.set(null);
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.uploadFile(file);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
    const file = event.dataTransfer?.files[0];
    if (file) {
      this.uploadFile(file);
    }
  }

  uploadFile(file: File): void {
    if (!file.name.toLowerCase().endsWith('.sql')) {
      this.uploadError.set('Solo se permiten archivos con extensión .sql.');
      return;
    }

    this.isUploading.set(true);
    this.uploadError.set('');
    const datasetName = file.name.replace(/\.sql$/i, '').trim() || 'Dataset importado';
    this.apiService.uploadDataset(datasetName, file).subscribe({
      next: (response) => {
        this.isUploading.set(false);
        this.loadDatasets(response.dataset_id);
        if (this.fileInput) {
          this.fileInput.nativeElement.value = '';
        }
      },
      error: (error) => {
        console.error('Error al importar dataset:', error);
        this.isUploading.set(false);
        this.uploadError.set(error.error?.detail || 'No se pudo importar el archivo SQL.');
      },
    });
  }

  deleteSelectedDataset(): void {
    const dataset = this.selectedDataset();
    if (!dataset || dataset.is_builtin) {
      return;
    }

    if (!confirm(`¿Eliminar el dataset "${dataset.name}"?`)) {
      return;
    }

    this.apiService.deleteDataset(dataset.dataset_id).subscribe({
      next: () => this.loadDatasets(),
      error: (error) => {
        console.error('Error al eliminar dataset:', error);
        this.datasetsError.set(error.error?.detail || 'No se pudo eliminar el dataset.');
      },
    });
  }

  loadHistory(): void {
    if (!this.currentUser()) {
      this.history.set([]);
      this.historyLoading.set(false);
      this.historyError.set('');
      return;
    }

    this.historyLoading.set(true);
    this.historyError.set('');

    const dataset = this.selectedDataset();
    const request = dataset
      ? this.apiService.getDatasetHistory(dataset.dataset_id)
      : this.apiService.getHistory();

    request.subscribe({
      next: (response) => {
        this.history.set(response.items);
        this.historyLoading.set(false);
      },

      error: (error) => {
        console.error('Error al cargar historial:', error);
        this.historyError.set('No se pudo cargar el historial.');
        this.historyLoading.set(false);
      },
    });
  }

  viewHistory(item: HistoryItem): void {
    this.selectedHistory.set(item);

    this.errorMessage.set('');
    this.question = '';

    this.chartInstance?.destroy();
    this.chartInstance = null;

    // Verificar que exista una copia de los resultados.
    if (!item.result_columns?.length || !item.result_rows?.length) {
      this.answer.set(null);
      return;
    }

    // Reconstruir la respuesta sin llamar a Microsoft Foundry.
    const restoredAnswer: AskResponse = {
      success: true,
      question: item.question,
      sql: item.generated_sql,
      columns: item.result_columns,
      rows: item.result_rows,
      row_count: item.row_count,
      truncated: item.truncated,
    };

    this.answer.set(restoredAnswer);

    // Volver a dibujar el gráfico con los resultados guardados.
    setTimeout(() => {
      this.renderChart(restoredAnswer);
    }, 0);
  }
}
