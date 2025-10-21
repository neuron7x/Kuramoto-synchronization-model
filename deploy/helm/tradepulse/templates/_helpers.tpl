{{- define "tradepulse.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tradepulse.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "tradepulse.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "tradepulse.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "tradepulse.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tradepulse.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "tradepulse.labels" -}}
helm.sh/chart: {{ include "tradepulse.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "tradepulse.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- if .Values.commonLabels }}
{{- toYaml .Values.commonLabels | nindent 0 }}
{{- end }}
{{- end -}}

{{- define "tradepulse.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "tradepulse.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "tradepulse.serviceAnnotations" -}}
{{- if .Values.service.annotations }}
{{- toYaml .Values.service.annotations -}}
{{- end -}}
{{- end -}}

{{- define "tradepulse.metricsServiceAnnotations" -}}
{{- if .Values.metricsService.annotations }}
{{- toYaml .Values.metricsService.annotations -}}
{{- end -}}
{{- end -}}

{{- define "tradepulse.image" -}}
{{- $repository := .Values.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- if .Values.image.digest -}}
{{ printf "%s@%s" $repository .Values.image.digest }}
{{- else -}}
{{ printf "%s:%s" $repository $tag }}
{{- end -}}
{{- end -}}
