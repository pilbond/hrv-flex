(() => {
    const UI_KEY = new URLSearchParams(window.location.search).get('key');
    const runtimeConfigEl = document.getElementById('ui-runtime-config');
    const UI_RUNTIME = runtimeConfigEl ? JSON.parse(runtimeConfigEl.textContent || '{}') : {};
    const UI_TEXT = UI_RUNTIME.text || {};
    const UI_TEMPLATES = UI_RUNTIME.templates || {};
    const SYNC_TIMEOUT_SEC = Number(UI_RUNTIME.sync_timeout_sec) || 1200;
    const POLL_INTERVAL_MS = 2000;
    const REFRESH_INTERVAL_MS = 30000;

    function el(id) {
        return document.getElementById(id);
    }

    function uiText(key) {
        return Object.prototype.hasOwnProperty.call(UI_TEXT, key) ? UI_TEXT[key] : '';
    }

    function uiTemplate(key) {
        return Object.prototype.hasOwnProperty.call(UI_TEMPLATES, key) ? UI_TEMPLATES[key] : '';
    }

    function renderTemplate(key, values) {
        const template = uiTemplate(key);
        return template.replace(/\{(\w+)\}/g, (_, placeholder) => {
            const value = values?.[placeholder];
            return value == null ? '' : String(value);
        });
    }

    const DOM = {
        status: el('status'),
        technicalOutput: el('rawOutput'),
        sync: {
            hrv: {
                button: el('syncBtn'),
                text: el('syncBtnText'),
                runningText: uiText('syncRunningHrv'),
                successText: uiText('syncSuccessHrv'),
            },
            sessions: {
                button: el('sessionsBtn'),
                text: el('sessionsBtnText'),
                runningText: uiText('syncRunningSessions'),
                successText: uiText('syncSuccessSessions'),
            },
        },
        auxiliary: {
            importSeed: {
                button: el('importBtn'),
                text: el('importBtnText'),
                runningText: uiText('importButtonRunning'),
            },
            restoreBackup: {
                button: el('restoreBackupBtn'),
                text: el('restoreBackupBtnText'),
                runningText: uiText('restoreButtonRunning'),
            },
            deleteLastRr: {
                button: el('deleteLastRrBtn'),
                text: el('deleteLastRrBtnText'),
                runningText: uiText('deleteButtonRunning'),
            },
        },
        hrvSummary: {
            card: el('hrvSummaryCard'),
            title: el('hrvSummaryTitle'),
            raw: el('hrvSummaryRaw'),
            used: el('hrvSummaryUsed'),
            base: el('hrvSummaryBase'),
            gate: el('hrvSummaryGate'),
            aiBlock: el('hrvSummaryAiBlock'),
            ai: el('hrvSummaryAi'),
            reasonBlock: el('hrvSummaryReasonBlock'),
            reason: el('hrvSummaryReason'),
            fallbackBlock: el('hrvSummaryFallbackBlock'),
            fallback: el('hrvSummaryFallback'),
        },
    };

    Object.values(DOM.sync).forEach(control => {
        if (control?.text) control.idleText = control.text.textContent.trim();
    });
    Object.values(DOM.auxiliary).forEach(control => {
        if (control?.text) control.idleText = control.text.textContent.trim();
    });

    function syncButtonConfig(jobType) {
        return DOM.sync[jobType] || null;
    }

    function apiFetch(url, options = {}) {
        const headers = Object.assign({}, options.headers || {});
        if (UI_KEY) headers['X-HRV-KEY'] = UI_KEY;
        return fetch(url, Object.assign({}, options, { headers }));
    }

    function showBanner(kind, message) {
        if (!DOM.status) return;
        DOM.status.className = `status ${kind} show`;
        DOM.status.textContent = message;
    }

    function renderTechnicalOutput(rawText) {
        if (!DOM.technicalOutput) return;
        DOM.technicalOutput.textContent = rawText || uiText('technicalOutputPlaceholder');
    }

    function renderHrvSummaryPanel(data) {
        const diagnostics = data?.diagnostics || {};
        const exists = Boolean(diagnostics.final_exists);
        const summaryDate = String(diagnostics.final_last_fecha || '').trim();
        const panel = DOM.hrvSummary;
        const titleBase = panel.title.dataset.titleBase || '';

        panel.card.hidden = !exists;
        panel.title.textContent = summaryDate ? `${titleBase} (${summaryDate})` : titleBase;

        if (!exists) {
            panel.raw.textContent = '-';
            panel.used.textContent = '-';
            panel.base.textContent = '-';
            panel.gate.textContent = '-';
            if (panel.aiBlock) panel.aiBlock.hidden = true;
            if (panel.reasonBlock) panel.reasonBlock.hidden = true;
            if (panel.fallbackBlock) panel.fallbackBlock.hidden = true;
            return;
        }

        const rmssdRaw = diagnostics.final_last_rmssd_stable;
        const hrToday = diagnostics.final_last_hr_today;
        const lnToday = diagnostics.final_last_lnrmssd_today;
        const lnUsed = diagnostics.final_last_lnrmssd_used;
        const lnBase = diagnostics.final_last_ln_base60;
        const swcLn = diagnostics.final_last_swc_ln;
        const gateBadge = diagnostics.final_last_gate_badge || 'N/A';
        const gateReason = diagnostics.final_last_gate_razon_base60 || 'N/A';
        const aiText = String(diagnostics.hrv_summary_ai_text || '').trim();
        const reasonText = String(diagnostics.hrv_summary_reason_text || '').trim();
        const fallbackText = String(diagnostics.hrv_summary_fallback_text || '').trim();
        const hasReasonText = Boolean(diagnostics.hrv_summary_has_reason_text);
        const reasonIsFallback = Boolean(diagnostics.hrv_summary_reason_is_fallback);

        panel.raw.textContent = `${fmtNumber(rmssdRaw)} ms · HR ${fmtNumber(hrToday)} lpm · lnRMSSD bruto ${fmtNumber(lnToday, 3)}`;
        panel.used.textContent = `${fmtNumber(expFromLog(lnUsed))} ms · lnRMSSD usado ${fmtNumber(lnUsed, 3)}`;
        panel.base.textContent = `${fmtNumber(expFromLog(lnBase))} ms · SWC_ln ${fmtNumber(swcLn, 3)}`;
        panel.gate.textContent = `${gateBadge} · ${gateReason}`;
        if (panel.aiBlock) panel.aiBlock.hidden = !aiText;
        if (panel.ai) panel.ai.textContent = aiText;
        if (panel.reasonBlock) panel.reasonBlock.hidden = !hasReasonText;
        if (panel.reason) panel.reason.textContent = reasonText;
        if (panel.fallbackBlock) panel.fallbackBlock.hidden = !reasonIsFallback;
        if (panel.fallback) panel.fallback.textContent = fallbackText;
    }

    function fmtNumber(value, decimals = 1) {
        const n = Number(value);
        return Number.isFinite(n) ? n.toFixed(decimals) : '-';
    }

    function expFromLog(value) {
        const n = Number(value);
        return Number.isFinite(n) ? Math.exp(n) : NaN;
    }

    function fmtDateFromRrName(value) {
        const raw = String(value || '').trim();
        const match = raw.match(/(\d{4})-(\d{2})-(\d{2})/);
        if (!match) return '';
        return `${match[3]}/${match[2]}/${match[1]}`;
    }

    function setSyncButtonsDisabled(disabled) {
        Object.values(DOM.sync).forEach(control => {
            if (control.button) control.button.disabled = disabled;
        });
    }

    function setAuxButtonDisabled(control, disabled) {
        if (control?.button) control.button.disabled = disabled;
    }

    function setButtonLoading(control) {
        if (!control?.button || !control?.text) return;
        control.button.disabled = true;
        control.text.innerHTML = `<span class="spinner"></span> ${control.runningText}`;
    }

    function resetAuxButton(control) {
        if (!control?.button || !control?.text) return;
        control.button.disabled = false;
        control.text.textContent = control.idleText;
    }

    function setButtonState(jobType, state) {
        const control = syncButtonConfig(jobType);
        if (!control?.button || !control?.text) return;

        control.button.classList.remove('running', 'success');
        if (state === 'running') {
            control.button.classList.add('running');
            control.text.innerHTML = `<span class="spinner"></span> ${control.runningText}`;
            return;
        }

        if (state === 'success') {
            control.button.classList.add('success');
            control.text.textContent = control.successText;
            return;
        }

        control.text.textContent = control.idleText;
    }

    function resetSyncButtons() {
        setButtonState('hrv', 'idle');
        setButtonState('sessions', 'idle');
    }

    function currentOutputText(data) {
        return data.last_output || data.output || data.last_error || '';
    }

    function currentErrorText(data) {
        return data.error || data.last_error || data.message || uiText('unknownError');
    }

    function runningBannerMessage(jobType) {
        return jobType === 'sessions'
            ? uiText('bannerRunningSessions')
            : uiText('bannerRunningHrv');
    }

    function pollRunningMessage(jobType, elapsedSec) {
        const jobLabel = jobType === 'sessions'
            ? uiText('pollStatusSessions')
            : uiText('pollStatusHrv');

        return renderTemplate('pollStatus', {
            jobLabel,
            minutes: Math.floor(elapsedSec / 60),
            seconds: elapsedSec % 60,
        });
    }

    function applyUiState(data) {
        const rawText = currentOutputText(data);
        resetSyncButtons();

        if (data.running && data.job_type === 'hrv') setButtonState('hrv', 'running');
        else if (data.running && data.job_type === 'sessions') setButtonState('sessions', 'running');

        setSyncButtonsDisabled(Boolean(data.running));
        setAuxButtonDisabled(DOM.auxiliary.importSeed, Boolean(data.running));

        const latestRrPath = data?.diagnostics?.latest_rr_path;
        setAuxButtonDisabled(DOM.auxiliary.deleteLastRr, Boolean(data.running || !latestRrPath));

        renderHrvSummaryPanel(data);
        renderTechnicalOutput(rawText);
    }

    async function refreshDashboard() {
        try {
            const response = await apiFetch('/api/status');
            const data = await response.json();

            applyUiState(data);

            if (data.running) {
                showBanner('info', runningBannerMessage(data.job_type));
            } else if (data.success === true) {
                showBanner('success', data.message || uiText('bannerLastSuccess'));
            } else if (data.success === false) {
                showBanner('error', data.last_error || data.message || uiText('bannerLastError'));
            }
        } catch (error) {
            console.error('Error actualizando status:', error);
        }
    }

    async function startJob(url, jobType, startMessage) {
        const control = syncButtonConfig(jobType);

        setSyncButtonsDisabled(true);
        setButtonState(jobType, 'running');
        showBanner('info', startMessage);

        try {
            const response = await apiFetch(url, { method: 'POST' });
            const data = await response.json();

            if (!response.ok) {
                showSyncError(data);
                return;
            }

            if (data.message && /iniciada/i.test(data.message)) {
                await pollSyncStatus();
            } else if (data.success) {
                showSyncSuccess(data, jobType);
            } else {
                showSyncError(data);
            }
        } catch (error) {
            if (control?.button) control.button.classList.remove('running');
            if (control?.text) control.text.textContent = control.idleText;
            setSyncButtonsDisabled(false);
            showBanner('error', uiText('bannerConnectionErrorPrefix') + error.message);
        }
    }

    async function importSeedCsvs() {
        const control = DOM.auxiliary.importSeed;

        setButtonLoading(control);
        showBanner('info', uiText('importStart'));

        try {
            const response = await apiFetch('/api/import-seed', { method: 'POST' });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Error importando CSV seed');
            renderTechnicalOutput(JSON.stringify(data, null, 2));
            showBanner('success', uiText('importSuccess'));
            await refreshDashboard();
        } catch (error) {
            showBanner('error', error.message);
        } finally {
            resetAuxButton(control);
        }
    }

    async function restoreFromDropbox() {
        const control = DOM.auxiliary.restoreBackup;
        const confirmed = window.confirm(uiText('restoreConfirm'));
        if (!confirmed) return;

        setButtonLoading(control);
        showBanner('info', uiText('restoreStart'));

        try {
            const response = await apiFetch('/api/restore-backup', { method: 'POST' });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Error restaurando backup');
            renderTechnicalOutput(JSON.stringify(data, null, 2));
            showBanner(
                'success',
                renderTemplate(
                    'restoreSuccess',
                    {
                        count: data.restored?.length || 0,
                        source: data.source_folder || uiText('restoreSuccessFallbackSource'),
                    },
                )
            );
            await refreshDashboard();
        } catch (error) {
            showBanner('error', error.message);
        } finally {
            resetAuxButton(control);
        }
    }

    async function deleteLastRr() {
        const control = DOM.auxiliary.deleteLastRr;
        const statusResponse = await apiFetch('/api/status');
        const statusData = await statusResponse.json();
        const latest = statusData?.diagnostics?.latest_rr_file;

        if (!latest) {
            showBanner('error', uiText('deleteNoLatest'));
            return;
        }

        const latestDate = fmtDateFromRrName(latest);
        const latestLabel = latestDate ? `${latest} (${latestDate})` : latest;
        const confirmed = window.confirm(
            renderTemplate('deleteConfirm', { label: latestLabel })
        );
        if (!confirmed) return;

        setButtonLoading(control);
        showBanner(
            'info',
            renderTemplate('deleteStart', { label: latestLabel })
        );

        try {
            const response = await apiFetch('/api/delete-latest-rr', { method: 'POST' });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Error borrando el último RR');
            renderTechnicalOutput(JSON.stringify(data, null, 2));
            showBanner(
                'success',
                renderTemplate('deleteSuccess', { name: data.deleted_rr_name })
            );
            await refreshDashboard();
        } catch (error) {
            showBanner('error', error.message);
        } finally {
            resetAuxButton(control);
        }
    }

    async function pollSyncStatus() {
        let attempts = 0;
        const maxAttempts = Math.ceil((SYNC_TIMEOUT_SEC * 1000) / POLL_INTERVAL_MS);

        while (attempts < maxAttempts) {
            await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
            try {
                const response = await apiFetch('/api/status');
                const data = await response.json();
                applyUiState(data);

                if (!data.running) {
                    if (data.success) showSyncSuccess(data, data.job_type);
                    else if (data.success === false) showSyncError(data);
                    return;
                }

                attempts++;
                const elapsedSec = attempts * (POLL_INTERVAL_MS / 1000);
                showBanner('info', pollRunningMessage(data.job_type, elapsedSec));
            } catch (error) {
                console.error('Error polling status:', error);
                attempts++;
            }
        }

        setSyncButtonsDisabled(false);
        resetSyncButtons();
        showBanner('error', uiText('pollTimeout'));
    }

    function showSyncSuccess(data, jobType) {
        setSyncButtonsDisabled(false);
        resetSyncButtons();
        if (jobType) setButtonState(jobType, 'success');
        renderTechnicalOutput(data.last_output || data.output || '');
        showBanner('success', data.message || uiText('processCompleted'));
        setTimeout(resetSyncButtons, 3000);
    }

    function showSyncError(data) {
        setSyncButtonsDisabled(false);
        resetSyncButtons();
        renderTechnicalOutput(data.last_output || data.output || data.error || data.last_error || uiText('unknownError'));
        showBanner('error', currentErrorText(data));
    }

    function bindSyncButtons() {
        Object.entries(DOM.sync).forEach(([jobType, control]) => {
            if (!control.button) return;
            control.button.addEventListener('click', async () => {
                const endpoint = jobType === 'sessions' ? '/api/sync-sessions' : '/api/sync';
                await startJob(
                    endpoint,
                    jobType,
                    jobType === 'sessions'
                        ? uiText('bannerStartSessions')
                        : uiText('bannerStartHrv')
                );
            });
        });
    }

    function bindAuxiliaryButtons() {
        if (DOM.auxiliary.importSeed.button) {
            DOM.auxiliary.importSeed.button.addEventListener('click', importSeedCsvs);
        }
        if (DOM.auxiliary.restoreBackup.button) {
            DOM.auxiliary.restoreBackup.button.addEventListener('click', restoreFromDropbox);
        }
        if (DOM.auxiliary.deleteLastRr.button) {
            DOM.auxiliary.deleteLastRr.button.addEventListener('click', deleteLastRr);
        }
    }

    bindSyncButtons();
    bindAuxiliaryButtons();
    setInterval(refreshDashboard, REFRESH_INTERVAL_MS);
    refreshDashboard();
})();
