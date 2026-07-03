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
        technicalToggle: el('technicalToggleBtn'),
        technicalToggleText: el('technicalToggleText'),
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
            qc: el('hrvSummaryQc'),
            quality: el('hrvSummaryQuality'),
            stability: el('hrvSummaryStability'),
            raw: el('hrvSummaryRaw'),
            used: el('hrvSummaryUsed'),
            base: el('hrvSummaryBase'),
            gateBadge: el('hrvSummaryGateBadge'),
            gateAction: el('hrvSummaryGateAction'),
            gateWhatHappened: el('hrvSummaryGateWhatHappened'),
            gateWhatToDo: el('hrvSummaryGateWhatToDo'),
            aiBlock: el('hrvSummaryAiBlock'),
            ai: el('hrvSummaryAi'),
            reasonBlock: el('hrvSummaryReasonBlock'),
            reason: el('hrvSummaryReason'),
            ssmBlock: el('hrvSummarySsmBlock'),
            ssm: el('hrvSummarySsm'),
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
        const hrv = data?.view?.hrv_today || {};
        const gate = hrv.gate || {};
        const panel = DOM.hrvSummary;
        const titleBase = panel.title.dataset.titleBase || '';
        const exists = Boolean(hrv.exists);
        const summaryDate = String(hrv.date || '').trim();

        panel.card.hidden = !exists;
        panel.title.textContent = summaryDate ? `${titleBase} (${summaryDate})` : titleBase;

        if (!exists) {
            panel.raw.textContent = '-';
            panel.used.textContent = '-';
            panel.base.textContent = '-';
            if (panel.qc) panel.qc.hidden = true;
            if (panel.quality) {
                panel.quality.textContent = '-';
                panel.quality.classList.remove('is-ok', 'is-warn');
            }
            if (panel.stability) {
                panel.stability.textContent = '-';
                panel.stability.classList.remove('is-ok', 'is-warn');
            }
            if (panel.gateBadge) panel.gateBadge.textContent = '-';
            if (panel.gateAction) panel.gateAction.textContent = '-';
            if (panel.gateWhatHappened) panel.gateWhatHappened.textContent = '-';
            if (panel.gateWhatToDo) panel.gateWhatToDo.textContent = '-';
            if (panel.aiBlock) panel.aiBlock.hidden = true;
            if (panel.reasonBlock) panel.reasonBlock.hidden = true;
            if (panel.ssmBlock) panel.ssmBlock.hidden = true;
            if (panel.fallbackBlock) panel.fallbackBlock.hidden = true;
            return;
        }

        const quality = String(hrv.quality || '').trim();
        const stability = String(hrv.stability || '').trim();
        const aiText = String(hrv.ai_text || '').trim();
        const reasonText = String(hrv.reason_text || '').trim();
        const ssmText = String(hrv.ssm_text || '').trim();
        const fallbackText = String(hrv.fallback_text || '').trim();

        panel.raw.textContent = String(hrv.raw_text || '-');
        panel.used.textContent = String(hrv.used_text || '-');
        panel.base.textContent = String(hrv.base_text || '-');
        if (panel.qc) panel.qc.hidden = !(quality || stability);
        if (panel.quality) {
            panel.quality.textContent = quality || '-';
            panel.quality.classList.toggle('is-ok', quality === 'OK');
            panel.quality.classList.toggle('is-warn', Boolean(quality) && quality !== 'OK');
        }
        if (panel.stability) {
            panel.stability.textContent = stability || '-';
            panel.stability.classList.toggle('is-ok', stability === 'OK');
            panel.stability.classList.toggle('is-warn', Boolean(stability) && stability !== 'OK');
        }
        if (panel.gateBadge) panel.gateBadge.textContent = String(gate.badge || '-');
        if (panel.gateAction) panel.gateAction.textContent = String(gate.action || '-');
        if (panel.gateWhatHappened) panel.gateWhatHappened.textContent = String(gate.what_happened || '-');
        if (panel.gateWhatToDo) panel.gateWhatToDo.textContent = String(gate.what_to_do || '-');
        if (panel.aiBlock) panel.aiBlock.hidden = !aiText;
        if (panel.ai) panel.ai.textContent = aiText;
        if (panel.reasonBlock) panel.reasonBlock.hidden = !reasonText;
        if (panel.reason) panel.reason.textContent = reasonText;
        if (panel.ssmBlock) panel.ssmBlock.hidden = !ssmText;
        if (panel.ssm) panel.ssm.textContent = ssmText;
        if (panel.fallbackBlock) panel.fallbackBlock.hidden = !fallbackText;
        if (panel.fallback) panel.fallback.textContent = fallbackText;
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

        const latestRrPath = data?.view?.system?.latest_rr_path;
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
        const system = statusData?.view?.system || {};
        const latest = system.latest_rr_file;

        if (!latest) {
            showBanner('error', uiText('deleteNoLatest'));
            return;
        }

        const latestLabel = system.latest_rr_label || latest;
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
        setTechnicalCollapsed(true);
        showBanner('success', data.message || uiText('processCompleted'));
        setTimeout(resetSyncButtons, 3000);
    }

    function showSyncError(data) {
        setSyncButtonsDisabled(false);
        resetSyncButtons();
        renderTechnicalOutput(data.last_output || data.output || data.error || data.last_error || uiText('unknownError'));
        setTechnicalCollapsed(false);
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

    function setTechnicalCollapsed(collapsed) {
        if (!DOM.technicalOutput) return;
        DOM.technicalOutput.classList.toggle('is-collapsed', collapsed);
        if (DOM.technicalToggle) {
            DOM.technicalToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }
        if (DOM.technicalToggleText) {
            DOM.technicalToggleText.textContent = collapsed
                ? uiText('technicalExpand') || 'Expandir'
                : uiText('technicalCollapse') || 'Contraer';
        }
    }

    function bindTechnicalToggle() {
        if (!DOM.technicalToggle) return;
        DOM.technicalToggle.addEventListener('click', () => {
            const collapsed = DOM.technicalOutput?.classList.contains('is-collapsed');
            setTechnicalCollapsed(!collapsed);
        });
    }

    bindSyncButtons();
    bindAuxiliaryButtons();
    bindTechnicalToggle();
    setInterval(refreshDashboard, REFRESH_INTERVAL_MS);
    refreshDashboard();
})();
