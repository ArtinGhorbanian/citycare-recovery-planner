// ============================================================================
// SECTION 1: APPLICATION STATE AND DOM ELEMENTS
// Keeps the latest API results and short links to the page elements.
// ============================================================================

var appState = {
    ready: false,
    backendReady: false,
    options: null,
    status: null,
    predictionResult: null,
    allocationResult: null,
    historyResult: null,
    currentView: "overview",
    hasPrediction: false,
    hasAllocation: false,
    predictionStale: false,
    allocationStale: false,
    showAllAllocationRows: false,
    aiInfo: null,
    scenarioRevision: 0,
    scenarioBasis: "Loading the latest dataset record",
    predictionGeneration: 0,
    lastPredictionSnapshot: null,
    chatStarted: false,
    drawerReturnFocus: null,
    latestRequestKind: null,
    pending: {
        latest: false,
        prediction: false,
        allocation: false,
        chat: false
    },
    requestCounters: {
        latest: 0,
        history: 0,
        prediction: 0,
        briefing: 0,
        allocation: 0,
        chat: 0
    },
    requestControllers: {},
    charts: {
        resource: null,
        historyRisk: null,
        historyResource: null
    }
};

// Small helper that returns one element by its id.
function element(elementId) {
    return document.getElementById(elementId);
}

// Fields of the crisis form, grouped so the code below stays short.
var crisisFields = {
    hospital: "hospitalSelect",
    timestamp: "incidentTimestamp",
    disasterType: "disasterTypeSelect",
    distance: "incidentDistance",
    ambulances: "ambulanceArrivals",
    arrivalRate: "patientArrivalRate",
    triage: "triageLevelSelect",
    injury: "injuryTypeSelect",
    treatmentTime: "treatmentTime",
    mortality: "mortalityRiskPercent",
    bedOccupancy: "bedOccupancyPercent",
    icuOccupancy: "icuOccupancyPercent",
    equipment: "equipmentUsagePercent",
    nurseRatio: "nurseRatio",
    doctors: "doctorsAvailable"
};


// ============================================================================
// SECTION 2: GENERAL HELPER FUNCTIONS
// Small text, number and DOM helpers used by the rest of the file.
// ============================================================================

// Write plain text into an element without using innerHTML.
function setText(elementId, textValue) {
    var target = element(elementId);
    if (target && target.textContent !== String(textValue)) {
        target.textContent = textValue;
    }
}

// Remove every child of an element in a safe way.
function clearElement(target) {
    while (target && target.firstChild) {
        target.removeChild(target.firstChild);
    }
}

// Show or hide one element.
function setVisible(elementId, isVisible) {
    var target = element(elementId);
    if (!target) {
        return;
    }
    if (isVisible) {
        target.classList.remove("hidden");
    } else {
        target.classList.add("hidden");
    }
}

// Format a number with a fixed number of decimals.
function formatNumber(value, decimals) {
    if (value === null || value === undefined || isNaN(value)) {
        return "not available";
    }
    return Number(value).toFixed(decimals);
}

// Turn a capacity status into the matching CSS class name.
function statusClassName(statusText) {
    if (statusText === "Stable") {
        return "is-stable";
    }
    if (statusText === "Warning") {
        return "is-warning";
    }
    if (statusText === "High Risk") {
        return "is-high";
    }
    return "";
}

// Turn a trend direction into the matching CSS class name.
function trendClassName(directionText) {
    if (directionText === "Worsening") {
        return "trend-worsening";
    }
    if (directionText === "Improving") {
        return "trend-improving";
    }
    return "trend-stable";
}

// Build one list item that holds a bold title and a normal description.
function createFactorItem(titleText, detailText) {
    var listItem = document.createElement("li");

    var titlePart = document.createElement("strong");
    titlePart.textContent = titleText;
    listItem.appendChild(titlePart);

    if (detailText) {
        var detailPart = document.createElement("span");
        detailPart.textContent = detailText;
        listItem.appendChild(detailPart);
    }

    return listItem;
}

// Fill one select element with option values from the configured dataset.
function fillSelect(selectId, valueList) {
    var target = element(selectId);
    if (!target) {
        return;
    }

    clearElement(target);
    for (var index = 0; index < valueList.length; index++) {
        var optionElement = document.createElement("option");
        optionElement.value = valueList[index];
        optionElement.textContent = valueList[index];
        target.appendChild(optionElement);
    }
}

// Move the reading position back to the top of the freshly opened view.
function scrollViewToTop() {
    var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
}

// Return the human-readable label of the hospital selected in Step 1.
function selectedHospitalLabel() {
    var select = element(crisisFields.hospital);
    if (!select || select.selectedIndex < 0) {
        return "No hospital selected";
    }
    return select.options[select.selectedIndex].textContent || "No hospital selected";
}

function displayScenarioTimestamp(timestampValue) {
    if (!timestampValue) {
        return "Not set";
    }
    var timezoneName = "local time";
    try {
        timezoneName = Intl.DateTimeFormat().resolvedOptions().timeZone || timezoneName;
    } catch (error) {
        // Older browsers still receive an explicit local-time label.
    }
    return String(timestampValue).replace("T", " ") + " · " + timezoneName;
}

// Start one request in a named channel. A newer request aborts and supersedes it.
function beginRequest(channelName) {
    var previousController = appState.requestControllers[channelName];
    if (previousController) {
        previousController.abort();
    }

    appState.requestCounters[channelName] += 1;
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    appState.requestControllers[channelName] = controller;

    return {
        id: appState.requestCounters[channelName],
        signal: controller ? controller.signal : null
    };
}

function cancelRequest(channelName) {
    var controller = appState.requestControllers[channelName];
    if (controller) {
        controller.abort();
    }
    appState.requestControllers[channelName] = null;
    appState.requestCounters[channelName] += 1;
}

function requestIsCurrent(channelName, requestTicket) {
    return requestTicket && appState.requestCounters[channelName] === requestTicket.id;
}

function finishRequest(channelName, requestTicket) {
    if (requestIsCurrent(channelName, requestTicket)) {
        appState.requestControllers[channelName] = null;
        return true;
    }
    return false;
}

function isAbortError(error) {
    return Boolean(error && error.name === "AbortError");
}

function setAppStatus(sourceName, toneName, titleText, messages) {
    var banner = element("appStatusBanner");
    if (!banner) {
        return;
    }
    banner.dataset.source = sourceName;
    banner.className = "message-box message-" + toneName;
    banner.setAttribute("role", toneName === "error" ? "alert" : "status");
    showListMessage("appStatusBanner", titleText, messages);
}

function clearAppStatus(sourceName) {
    var banner = element("appStatusBanner");
    if (banner && (!sourceName || banner.dataset.source === sourceName)) {
        setVisible("appStatusBanner", false);
        banner.removeAttribute("data-source");
    }
}

function refreshWorkflowControls() {
    var ready = appState.ready === true;
    var latestLocksScenario = appState.pending.latest && appState.latestRequestKind !== "manual";
    var controlRules = [
        ["analyzeButton", !ready || appState.pending.prediction || appState.pending.latest],
        ["loadLatestButton", !ready || appState.pending.latest],
        ["buildAllocationButton", !ready || appState.pending.allocation || appState.pending.latest],
        ["chatSendButton", !ready || appState.pending.chat]
    ];

    for (var index = 0; index < controlRules.length; index++) {
        var control = element(controlRules[index][0]);
        if (control) {
            control.disabled = controlRules[index][1];
        }
    }

    var hospitalSelect = element(crisisFields.hospital);
    if (hospitalSelect) {
        hospitalSelect.disabled = !ready;
    }

    var crisisForm = element("crisisForm");
    if (crisisForm) {
        var crisisFieldsets = crisisForm.querySelectorAll("fieldset");
        for (var fieldsetIndex = 0; fieldsetIndex < crisisFieldsets.length; fieldsetIndex++) {
            crisisFieldsets[fieldsetIndex].disabled = !ready || latestLocksScenario;
        }
    }

    var chatInput = element("chatInput");
    if (chatInput) {
        chatInput.disabled = !ready || appState.pending.chat;
    }

    var downloadButton = element("downloadAllocationButton");
    if (downloadButton) {
        downloadButton.disabled = !ready || !appState.hasAllocation || appState.allocationStale;
    }

    var chatChips = document.querySelectorAll(".chat-chip");
    for (var chipIndex = 0; chipIndex < chatChips.length; chipIndex++) {
        chatChips[chipIndex].disabled = !ready || appState.pending.chat;
    }

    var chatLog = element("chatLog");
    if (chatLog) {
        chatLog.setAttribute("aria-busy", appState.pending.chat ? "true" : "false");
    }
}

function updateScenarioStrip() {
    var strip = element("scenarioStrip");
    if (!strip || !appState.options) {
        return;
    }

    setVisible("scenarioStrip", true);
    setText("scenarioHospital", selectedHospitalLabel());
    setText("scenarioTimestamp", displayScenarioTimestamp(element(crisisFields.timestamp).value));
    setText("scenarioBasis", appState.scenarioBasis);

    var state = element("scenarioState");
    if (!state) {
        return;
    }
    if (appState.hasPrediction && appState.predictionStale) {
        state.textContent = "Prediction stale · analyze again";
        state.className = "scenario-state is-stale";
    } else if (appState.hasPrediction) {
        state.textContent = "Prediction current";
        state.className = "scenario-state is-current";
    } else {
        state.textContent = "Draft · not analyzed";
        state.className = "scenario-state is-draft";
    }
}

function invalidatePrediction(reasonText) {
    cancelRequest("prediction");
    cancelRequest("briefing");
    if (appState.pending.prediction) {
        appState.pending.prediction = false;
        setButtonLoading("analyzeButton", false, "Analyze Crisis and Build Recovery Plan");
    }

    if (appState.hasPrediction) {
        appState.predictionStale = true;
        setText("predictionStaleText", reasonText || "The scenario changed after this result was calculated.");
        setVisible("predictionStaleNotice", true);
    }
    updateNavigationState();
    updateScenarioStrip();
    refreshWorkflowControls();
}

function invalidateAllocation(reasonText) {
    cancelRequest("allocation");
    if (appState.pending.allocation) {
        appState.pending.allocation = false;
        setButtonLoading("buildAllocationButton", false, "Build Allocation Plan");
    }

    if (appState.hasAllocation) {
        appState.allocationStale = true;
        setText("allocationStaleText", reasonText ||
            "The reserve, priorities or selected scenario changed after this report was built.");
        setVisible("allocationStaleNotice", true);
    }
    updateNavigationState();
    refreshWorkflowControls();
}

function markScenarioEdited(reasonText) {
    appState.scenarioRevision += 1;
    appState.scenarioBasis = "Edited current scenario";
    invalidatePrediction(reasonText || "A Step 1 value changed after this result was calculated.");
    if (element("useCurrentScenario").checked) {
        invalidateAllocation("The current Step 1 scenario changed after this report was built.");
    }
    updateScenarioStrip();
}

function cancelPendingLatestRecordForManualEdit() {
    if (!appState.pending.latest || appState.latestRequestKind !== "manual") {
        return;
    }
    cancelRequest("latest");
    appState.pending.latest = false;
    appState.latestRequestKind = null;
    setButtonLoading("loadLatestButton", false, "Load Latest Dataset Record");
    refreshWorkflowControls();
}

function clearFieldError(field) {
    if (!field) {
        return;
    }
    field.removeAttribute("aria-invalid");
    var errorId = field.dataset.validationErrorId;
    if (errorId) {
        var errorNode = element(errorId);
        if (errorNode && errorNode.parentNode) {
            errorNode.parentNode.removeChild(errorNode);
        }
        var describedBy = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (value) {
            return value && value !== errorId;
        });
        if (describedBy.length > 0) {
            field.setAttribute("aria-describedby", describedBy.join(" "));
        } else {
            field.removeAttribute("aria-describedby");
        }
        delete field.dataset.validationErrorId;
    }
}

function clearValidationErrors(formId) {
    var form = element(formId);
    if (!form) {
        return;
    }
    var invalidFields = form.querySelectorAll("[aria-invalid='true']");
    for (var index = 0; index < invalidFields.length; index++) {
        clearFieldError(invalidFields[index]);
    }
}

function addValidationError(fieldId, messageText, errors) {
    errors.push(messageText);
    var field = element(fieldId);
    if (!field) {
        return;
    }
    clearFieldError(field);
    var errorId = fieldId + "-error";
    var error = document.createElement("small");
    error.className = "field-error";
    error.id = errorId;
    error.textContent = messageText;
    var fieldContainer = field.closest ? field.closest(".field") : field.parentNode;
    if (fieldContainer) {
        fieldContainer.appendChild(error);
    }
    field.setAttribute("aria-invalid", "true");
    var describedBy = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    describedBy.push(errorId);
    field.setAttribute("aria-describedby", describedBy.join(" "));
    field.dataset.validationErrorId = errorId;
}

function focusFirstInvalid(formId) {
    var form = element(formId);
    var invalidField = form ? form.querySelector("[aria-invalid='true']") : null;
    if (invalidField) {
        invalidField.focus();
    }
}


// ============================================================================
// SECTION 3: API REQUEST HELPER
// One small function that talks to the Flask API and reports clear errors.
// ============================================================================

function requestApi(path, method, bodyObject, abortSignal) {
    var settings = { method: method, headers: { "Content-Type": "application/json" } };
    if (bodyObject) {
        settings.body = JSON.stringify(bodyObject);
    }
    if (abortSignal) {
        settings.signal = abortSignal;
    }

    return fetch(path, settings).then(function (response) {
        return response.json().catch(function () {
            throw new Error("The server answer could not be read.");
        }).then(function (data) {
            if (!response.ok) {
                var message = "The request failed with status " + response.status + ".";
                if (data && data.error) {
                    message = data.error;
                }
                throw new Error(message);
            }
            return data;
        });
    });
}


// ============================================================================
// SECTION 4: LOAD STATUS AND DATASET OPTIONS
// Reads /api/status and /api/options and fills the overview and the dropdowns.
// ============================================================================

function loadStatus() {
    return requestApi("/api/status", "GET", null).then(function (status) {
        appState.status = status;
        appState.backendReady = status.ready === true;

        if (!appState.backendReady) {
            var message = "The dataset or the models could not be prepared.";
            if (status.startup_error) {
                message = message + " Details: " + status.startup_error;
            }
            showStartupError(message);
            return status;
        }

        showDatasetOverview(status.dataset);
        showModelQuality(status);
        showAiStatus(status.ai);
        return status;
    });
}

// Explain in plain words whether the optional language model is switched on.
function showAiStatus(aiInfo) {
    appState.aiInfo = aiInfo;

    if (!aiInfo) {
        setText("aiStatusText", "The language model helper is not configured.");
        setText("assistantModeNote", "Rule-based mode: answers are written from fixed rules and configured dataset values.");
        return;
    }

    if (aiAssistedModeAvailable(aiInfo)) {
        setText("aiStatusText", "Switched on, using the model " + aiInfo.model + ". " + aiInfo.note);
        setText("assistantModeNote", "Assisted mode: " + aiInfo.model +
            " rewords the answers, and the exact values stay listed under each one.");
    } else if (aiInfo.enabled === true) {
        var fallbackReason = aiInfo.configuration_valid ?
            "the language-model service is currently unavailable" :
            "the language-model configuration is incomplete or invalid";
        setText("aiStatusText", "Language-model assistance is switched on, but " + fallbackReason +
            ". The planner is safely using fixed rules instead.");
        setText("assistantModeNote", "Fixed-rule fallback: language-model assistance is enabled but unavailable. " +
            "Answers still use the configured dataset and model values.");
    } else {
        setText("aiStatusText", "Switched off. Every answer and briefing is written by fixed rules from the configured dataset and model values. " +
            "Set AI_ENABLED=true in the .env file to switch it on.");
        setText("assistantModeNote", "Rule-based mode: answers are written from fixed rules and configured dataset values.");
    }
}

function aiAssistedModeAvailable(aiInfo) {
    return Boolean(aiInfo && aiInfo.enabled === true && aiInfo.available === true &&
        aiInfo.configuration_valid === true);
}

function showDatasetOverview(dataset) {
    setText("statTotalRecords", String(dataset.row_count));
    setText("statHospitals", String(dataset.hospital_count));
    setText("statDateRange", dataset.start_timestamp + "  to  " + dataset.end_timestamp);
    setText("statLatestTimestamp", dataset.latest_timestamp);
    setText("statStable", String(dataset.stable_records));
    setText("statWarning", String(dataset.warning_records));
    setText("statHighRisk", String(dataset.high_risk_records));
    setText("statTopDisaster", dataset.most_common_disaster_type);
}

function showModelQuality(status) {
    // Classification cards.
    setText("accuracyValue", formatNumber(status.classification_metrics.accuracy * 100, 1) + "%");
    setText("macroF1Value", formatNumber(status.classification_metrics.macro_f1, 3));
    setText("testPeriodValue", status.split.test_start + " to " + status.split.test_end);
    setText("testRowsValue", String(status.split.test_rows) + " test records");
    setText("trainPeriodValue", status.split.train_start + " to " + status.split.train_end);
    setText("trainRowsValue", String(status.split.train_rows) + " training records");

    // Regression table.
    var tableBody = element("regressionTableBody");
    clearElement(tableBody);

    for (var index = 0; index < status.regression_metrics.length; index++) {
        var metric = status.regression_metrics[index];
        var row = document.createElement("tr");

        var nameCell = document.createElement("td");
        nameCell.textContent = metric.label;
        row.appendChild(nameCell);

        var r2Cell = document.createElement("td");
        r2Cell.textContent = formatNumber(metric.r2, 3);
        row.appendChild(r2Cell);

        var maeCell = document.createElement("td");
        maeCell.textContent = formatNumber(metric.mae, 3);
        row.appendChild(maeCell);

        var unitCell = document.createElement("td");
        unitCell.textContent = metric.unit;
        row.appendChild(unitCell);

        tableBody.appendChild(row);
    }

    // Feature importance list with a simple proportional bar.
    var importanceList = element("featureImportanceList");
    clearElement(importanceList);

    var largestImportance = 0;
    for (var i = 0; i < status.feature_importances.length; i++) {
        if (status.feature_importances[i].importance > largestImportance) {
            largestImportance = status.feature_importances[i].importance;
        }
    }

    for (var j = 0; j < status.feature_importances.length; j++) {
        var item = status.feature_importances[j];
        var listItem = document.createElement("li");

        var head = document.createElement("div");
        head.className = "importance-head";

        var nameSpan = document.createElement("span");
        nameSpan.textContent = item.label;
        head.appendChild(nameSpan);

        var valueSpan = document.createElement("span");
        valueSpan.textContent = formatNumber(item.importance, 4);
        head.appendChild(valueSpan);

        listItem.appendChild(head);

        var bar = document.createElement("div");
        bar.className = "importance-bar";
        var widthPercent = 2;
        if (largestImportance > 0) {
            widthPercent = (item.importance / largestImportance) * 100;
        }
        bar.style.width = widthPercent + "%";
        listItem.appendChild(bar);

        importanceList.appendChild(listItem);
    }

    // Deeper methodology text.
    setText("modelNamesText", status.model_names.regression + " and " + status.model_names.classification);
    setText("methodologyLabelText", status.methodology_label);
    setText("excludedColumnsText", status.excluded_input_columns.join(", "));

    var recallParts = [];
    var recallData = status.classification_metrics.per_class_recall;
    for (var labelName in recallData) {
        if (Object.prototype.hasOwnProperty.call(recallData, labelName)) {
            if (recallData[labelName] === null) {
                recallParts.push(labelName + ": not available");
            } else {
                recallParts.push(labelName + ": " + formatNumber(recallData[labelName], 3));
            }
        }
    }
    setText("perClassRecallText", recallParts.join("   |   "));

    showConfusionMatrix(status.classification_metrics);
}

function showConfusionMatrix(classificationMetrics) {
    var headRow = element("confusionHeadRow");
    clearElement(headRow);

    var cornerCell = document.createElement("th");
    cornerCell.setAttribute("scope", "col");
    cornerCell.textContent = "Observed status";
    headRow.appendChild(cornerCell);

    for (var index = 0; index < classificationMetrics.labels.length; index++) {
        var headCell = document.createElement("th");
        headCell.setAttribute("scope", "col");
        headCell.textContent = "Predicted " + classificationMetrics.labels[index];
        headRow.appendChild(headCell);
    }

    var tableBody = element("confusionTableBody");
    clearElement(tableBody);

    for (var rowIndex = 0; rowIndex < classificationMetrics.confusion_matrix.length; rowIndex++) {
        var row = document.createElement("tr");

        var labelCell = document.createElement("th");
        labelCell.setAttribute("scope", "row");
        labelCell.textContent = classificationMetrics.labels[rowIndex];
        row.appendChild(labelCell);

        var values = classificationMetrics.confusion_matrix[rowIndex];
        for (var columnIndex = 0; columnIndex < values.length; columnIndex++) {
            var valueCell = document.createElement("td");
            valueCell.textContent = String(values[columnIndex]);
            row.appendChild(valueCell);
        }

        tableBody.appendChild(row);
    }
}

function loadOptions() {
    return requestApi("/api/options", "GET", null).then(function (options) {
        appState.options = options;

        // The hospital dropdown uses identifiers from the configured dataset.
        var hospitalSelect = element(crisisFields.hospital);
        clearElement(hospitalSelect);
        for (var index = 0; index < options.hospitals.length; index++) {
            var optionElement = document.createElement("option");
            optionElement.value = String(options.hospitals[index].id);
            optionElement.textContent = options.hospitals[index].label;
            hospitalSelect.appendChild(optionElement);
        }

        fillSelect(crisisFields.disasterType, options.disaster_types);
        fillSelect(crisisFields.triage, options.triage_levels);
        fillSelect(crisisFields.injury, options.injury_types);

        return options;
    });
}


// ============================================================================
// SECTION 5: LOAD LATEST HOSPITAL RECORD
// Fills the crisis form with the latest configured dataset record for one hospital.
// ============================================================================

function loadLatestRecord(hospitalId, requestKind) {
    var requestTicket = beginRequest("latest");
    appState.pending.latest = true;
    appState.latestRequestKind = requestKind || "required";
    setButtonLoading("loadLatestButton", true, "Load Latest Dataset Record");
    refreshWorkflowControls();

    return requestApi("/api/hospital/" + hospitalId + "/latest", "GET", null, requestTicket.signal).then(function (record) {
        if (!requestIsCurrent("latest", requestTicket) ||
                String(element(crisisFields.hospital).value) !== String(hospitalId)) {
            return null;
        }

        element(crisisFields.timestamp).value = record.timestamp_input;
        element(crisisFields.disasterType).value = record.disaster_type;
        element(crisisFields.triage).value = record.triage_level;
        element(crisisFields.injury).value = record.injury_type;

        element(crisisFields.distance).value = record.incident_distance_km;
        element(crisisFields.ambulances).value = record.ambulance_arrivals_per_hour;
        element(crisisFields.arrivalRate).value = record.patient_arrival_rate;
        element(crisisFields.treatmentTime).value = record.avg_treatment_time_min;
        element(crisisFields.mortality).value = record.mortality_risk_percent;
        element(crisisFields.bedOccupancy).value = record.bed_occupancy_percent;
        element(crisisFields.icuOccupancy).value = record.icu_occupancy_percent;
        element(crisisFields.equipment).value = record.equipment_usage_percent;
        element(crisisFields.nurseRatio).value = record.nurse_to_patient_ratio;
        element(crisisFields.doctors).value = record.doctor_available;

        setText("latestRecordNote", record.hospital_label + " - recorded at " + record.timestamp +
            ". You can change any value to describe a new condition.");
        setText("topbarHospital", record.hospital_label);
        appState.scenarioBasis = "Latest dataset record · " + record.timestamp;
        clearValidationErrors("crisisForm");
        setVisible("formErrorBox", false);
        updateScenarioStrip();

        return record;
    }).catch(function (error) {
        if (isAbortError(error) || !requestIsCurrent("latest", requestTicket)) {
            return null;
        }
        throw error;
    }).then(function (record) {
        if (finishRequest("latest", requestTicket)) {
            appState.pending.latest = false;
            appState.latestRequestKind = null;
            setButtonLoading("loadLatestButton", false, "Load Latest Dataset Record");
            refreshWorkflowControls();
        }
        return record;
    }, function (error) {
        if (finishRequest("latest", requestTicket)) {
            appState.pending.latest = false;
            appState.latestRequestKind = null;
            setButtonLoading("loadLatestButton", false, "Load Latest Dataset Record");
            refreshWorkflowControls();
        }
        throw error;
    });
}


// ============================================================================
// SECTION 6: READ AND VALIDATE THE CRISIS FORM
// Checks the entered values in the browser before they are sent to the server.
// ============================================================================

// Read one numeric field and check that it is a normal finite number.
function readNumericField(fieldId, labelText, minimumValue, maximumValue, errors) {
    var rawValue = element(fieldId).value;

    if (rawValue === null || String(rawValue).trim() === "") {
        addValidationError(fieldId, labelText + " is required.", errors);
        return null;
    }

    var numberValue = Number(rawValue);
    if (isNaN(numberValue) || !isFinite(numberValue)) {
        addValidationError(fieldId, labelText + " must be a normal number.", errors);
        return null;
    }

    if (numberValue < minimumValue) {
        addValidationError(fieldId, labelText + " cannot be below " + minimumValue + ".", errors);
        return null;
    }

    if (maximumValue !== null && numberValue > maximumValue) {
        addValidationError(fieldId, labelText + " cannot be above " + maximumValue + ".", errors);
        return null;
    }

    return numberValue;
}

function readWholeNumberField(fieldId, labelText, minimumValue, errors) {
    var numberValue = readNumericField(fieldId, labelText, minimumValue, null, errors);
    if (numberValue !== null && Math.floor(numberValue) !== numberValue) {
        addValidationError(fieldId, labelText + " must be a whole number.", errors);
        return null;
    }
    return numberValue;
}

// Build the snapshot object that both /api/predict and /api/allocate accept.
function readCrisisForm() {
    clearValidationErrors("crisisForm");
    var errors = [];
    var snapshot = {};

    var hospitalValue = element(crisisFields.hospital).value;
    if (!hospitalValue) {
        addValidationError(crisisFields.hospital, "Please choose a hospital.", errors);
    } else {
        snapshot.hospital_id = Number(hospitalValue);
    }

    var timestampValue = element(crisisFields.timestamp).value;
    if (!timestampValue) {
        addValidationError(crisisFields.timestamp, "Please choose a date and time.", errors);
    } else {
        snapshot.timestamp = timestampValue;
    }

    var categoryFields = [
        [crisisFields.disasterType, "disaster_type", "Disaster type"],
        [crisisFields.triage, "triage_level", "Triage level"],
        [crisisFields.injury, "injury_type", "Injury type"]
    ];

    for (var index = 0; index < categoryFields.length; index++) {
        var fieldId = categoryFields[index][0];
        var keyName = categoryFields[index][1];
        var labelText = categoryFields[index][2];
        var selectedValue = element(fieldId).value;

        if (!selectedValue) {
            addValidationError(fieldId, labelText + " is required.", errors);
        } else {
            snapshot[keyName] = selectedValue;
        }
    }

    snapshot.incident_distance_km = readNumericField(crisisFields.distance, "Distance from incident", 0, null, errors);
    snapshot.ambulance_arrivals_per_hour = readNumericField(crisisFields.ambulances, "Ambulances arriving each hour", 0, null, errors);
    snapshot.patient_arrival_rate = readNumericField(crisisFields.arrivalRate, "Patient arrival rate", 0, null, errors);
    snapshot.avg_treatment_time_min = readNumericField(crisisFields.treatmentTime, "Average treatment time", 0, null, errors);
    snapshot.nurse_to_patient_ratio = readNumericField(crisisFields.nurseRatio, "Nurse-to-patient ratio", 0, null, errors);
    snapshot.doctor_available = readNumericField(crisisFields.doctors, "Doctors currently available", 0, null, errors);

    // Percentage fields are entered from 0 to 100 and sent as decimals from 0 to 1.
    var mortalityPercent = readNumericField(crisisFields.mortality, "Mortality risk", 0, 100, errors);
    var bedPercent = readNumericField(crisisFields.bedOccupancy, "Bed occupancy", 0, 100, errors);
    var icuPercent = readNumericField(crisisFields.icuOccupancy, "ICU occupancy", 0, 100, errors);
    var equipmentPercent = readNumericField(crisisFields.equipment, "Equipment usage", 0, 100, errors);

    if (mortalityPercent !== null) {
        snapshot.mortality_risk_score = mortalityPercent / 100;
    }
    if (bedPercent !== null) {
        snapshot.bed_occupancy_rate = bedPercent / 100;
    }
    if (icuPercent !== null) {
        snapshot.icu_occupancy_rate = icuPercent / 100;
    }
    if (equipmentPercent !== null) {
        snapshot.equipment_usage_rate = equipmentPercent / 100;
    }

    return { snapshot: snapshot, errors: errors };
}


// ============================================================================
// SECTION 7: REQUEST AND DISPLAY PREDICTIONS
// Sends the crisis snapshot to /api/predict and paints the six result cards.
// ============================================================================

function handleCrisisSubmit(submitEvent) {
    submitEvent.preventDefault();

    if (!appState.ready || appState.pending.prediction) {
        return;
    }

    var formData = readCrisisForm();
    if (formData.errors.length > 0) {
        showListMessage("formErrorBox", "Please correct these fields", formData.errors);
        focusFirstInvalid("crisisForm");
        return;
    }
    setVisible("formErrorBox", false);

    cancelRequest("briefing");
    var requestTicket = beginRequest("prediction");
    var submittedRevision = appState.scenarioRevision;
    var submittedSnapshot = JSON.parse(JSON.stringify(formData.snapshot));
    appState.pending.prediction = true;
    setButtonLoading("analyzeButton", true, "Analyze Crisis and Build Recovery Plan");
    refreshWorkflowControls();

    requestApi("/api/predict", "POST", formData.snapshot, requestTicket.signal).then(function (result) {
        if (!requestIsCurrent("prediction", requestTicket)) {
            return null;
        }
        appState.predictionResult = result;
        appState.hasPrediction = true;
        appState.predictionStale = submittedRevision !== appState.scenarioRevision;
        appState.lastPredictionSnapshot = submittedSnapshot;
        appState.predictionGeneration += 1;
        showPredictionResult(result, submittedSnapshot);
        showRecoveryStrategies(result);
        showDecisionRecommendations(result);
        setVisible("predictionStaleNotice", appState.predictionStale);
        if (appState.predictionStale) {
            setText("predictionStaleText", "A Step 1 value changed while this prediction was being calculated.");
        }
        updateNavigationState();
        showView("results");
        updateScenarioStrip();
        loadBriefing(submittedSnapshot, appState.predictionGeneration);
        return result;
    }).catch(function (error) {
        if (!isAbortError(error) && requestIsCurrent("prediction", requestTicket)) {
            showListMessage("formErrorBox", "The analysis could not be completed", [error.message]);
        }
    }).then(function () {
        if (finishRequest("prediction", requestTicket)) {
            appState.pending.prediction = false;
            setButtonLoading("analyzeButton", false, "Analyze Crisis and Build Recovery Plan");
            refreshWorkflowControls();
        }
    });
}

function showPredictionResult(result, snapshot) {
    setVisible("resultsEmpty", false);
    setVisible("resultsContent", true);

    var predictions = result.predictions;

    setText("resultProvenanceHospital", result.hospital_label || selectedHospitalLabel());
    setText("resultProvenanceTimestamp", displayScenarioTimestamp(snapshot.timestamp));
    setText("resultProvenanceReceived", new Date().toLocaleString());
    setText("resultProvenanceBasis", appState.scenarioBasis);

    setText("cardPatientsValue", String(predictions.patients_next_2h.value));
    setText("cardPatientsRange", "Likely model range: " + predictions.patients_next_2h.low + " to " + predictions.patients_next_2h.high);

    setText("cardIcuValue", String(predictions.icu_beds.value));
    setText("cardIcuRange", "Likely model range: " + predictions.icu_beds.low + " to " + predictions.icu_beds.high);

    setText("cardVentValue", String(predictions.ventilators.value));
    setText("cardVentRange", "Likely model range: " + predictions.ventilators.low + " to " + predictions.ventilators.high);

    setText("cardStaffValue", String(predictions.staff.value));
    setText("cardStaffRange", "Likely model range: " + predictions.staff.low + " to " + predictions.staff.high);

    setText("cardOverloadValue", formatNumber(predictions.overload_risk.value, 1) + "%");
    setText("cardOverloadRange", "Likely model range: " + formatNumber(predictions.overload_risk.low, 1) +
        "% to " + formatNumber(predictions.overload_risk.high, 1) + "%");

    // The capacity status always shows text as well as colour.
    setText("cardStatusValue", result.capacity.status);
    setText("cardStatusConfidence", "Model confidence: " + formatNumber(result.capacity.confidence_percent, 1) + "%");

    var statusBadge = element("cardStatusBadge");
    statusBadge.textContent = result.capacity.status;
    statusBadge.className = "status-badge " + statusClassName(result.capacity.status);

    var statusCard = element("cardStatus");
    statusCard.className = "card result-card " + statusClassName(result.capacity.status);

    // Resilience card.
    setText("resilienceScore", formatNumber(result.resilience.index, 1) + " / 100");
    setText("resilienceStatus", result.resilience.status);
    setText("resilienceFormula", result.resilience.formula + ".");
    element("resilienceBar").style.width = result.resilience.index + "%";

    // Input range warnings.
    if (result.warnings && result.warnings.length > 0) {
        showListMessage("rangeWarningsBox", "Input range notices", result.warnings);
    } else {
        setVisible("rangeWarningsBox", false);
    }

    showPressureFactors(result.pressure_factors);
    showSimilarCases(result.similar_cases);
    populateResourceDataTable(result);
}

// Ask the server for the written briefing that belongs to this exact situation.
function loadBriefing(snapshot, predictionGeneration) {
    var requestTicket = beginRequest("briefing");
    setText("briefingSummary", "Preparing the briefing...");
    clearElement(element("briefingRecommendations"));
    setText("briefingSourceNote", "");

    requestApi("/api/briefing", "POST", snapshot, requestTicket.signal).then(function (briefing) {
        if (requestIsCurrent("briefing", requestTicket) &&
                predictionGeneration === appState.predictionGeneration && !appState.predictionStale) {
            showBriefing(briefing);
        }
    }).catch(function (error) {
        if (!isAbortError(error) && requestIsCurrent("briefing", requestTicket)) {
            setText("briefingSummary", "The briefing could not be created: " + error.message);
            setText("briefingSourceNote", "The prediction values above are not affected by this.");
        }
    }).then(function () {
        finishRequest("briefing", requestTicket);
    });
}

function showBriefing(briefing) {
    setText("briefingSummary", briefing.summary);

    var list = element("briefingRecommendations");
    clearElement(list);
    for (var index = 0; index < briefing.recommendations.length; index++) {
        var listItem = document.createElement("li");
        var text = document.createElement("span");
        text.textContent = briefing.recommendations[index];
        listItem.appendChild(text);
        list.appendChild(listItem);
    }

    // The label always says who wrote the wording, so nothing looks more certain than it is.
    var tag = element("briefingSourceTag");
    if (briefing.ai_used) {
        tag.textContent = "Model-worded";
        tag.className = "source-tag is-ai";
    } else {
        tag.textContent = "Rule-based";
        tag.className = "source-tag";
    }

    var note = briefing.source_note;
    if (briefing.ai_error) {
        note = note + " The language model was not used: " + briefing.ai_error;
    }
    setText("briefingSourceNote", note);
}

function showPressureFactors(factors) {
    var list = element("pressureFactorsList");
    clearElement(list);

    for (var index = 0; index < factors.length; index++) {
        list.appendChild(createFactorItem(factors[index].title, factors[index].detail));
    }
}

function showSimilarCases(similarCases) {
    if (!similarCases || similarCases.count === 0) {
        setVisible("similarCasesEmpty", true);
        setVisible("similarCasesList", false);
        setText("similarFilterNote", similarCases && similarCases.message ? similarCases.message : "No comparable record was found.");
        return;
    }

    setVisible("similarCasesEmpty", false);
    setVisible("similarCasesList", true);
    setText("similarFilterNote", "Dataset rows selected with this filter: " + similarCases.filter_used + ".");

    setText("similarCount", String(similarCases.count));
    setText("similarHighRisk", formatNumber(similarCases.high_risk_percent, 1) + "%");
    setText("similarPatients", formatNumber(similarCases.avg_patients_next_2h, 1));
    setText("similarIcu", formatNumber(similarCases.avg_required_icu_beds, 1));
    setText("similarVent", formatNumber(similarCases.avg_required_ventilators, 1));
    setText("similarStaff", formatNumber(similarCases.avg_required_staff, 1));
    setText("similarOverload", formatNumber(similarCases.avg_overload_risk_percent, 1) + "%");
    setText("similarOverloadRange", formatNumber(similarCases.min_overload_risk_percent, 1) + "% to " +
        formatNumber(similarCases.max_overload_risk_percent, 1) + "%");
    setText("similarStatus", similarCases.most_common_capacity_status);
}


// ============================================================================
// SECTION 8: DISPLAY RECOVERY STRATEGIES
// Renders only the strategy text that the server returned.
// ============================================================================

function fillStrategyList(listId, items) {
    var list = element(listId);
    clearElement(list);

    for (var index = 0; index < items.length; index++) {
        var listItem = document.createElement("li");
        listItem.textContent = items[index];
        list.appendChild(listItem);
    }
}

function showRecoveryStrategies(result) {
    setVisible("strategiesEmpty", false);
    setVisible("strategiesContent", true);

    var strategies = result.recovery_strategies;
    fillStrategyList("strategyActNow", strategies.immediate_priorities);
    fillStrategyList("strategyPrepare", strategies.next_two_hours);
    fillStrategyList("strategyWatch", strategies.monitoring_priorities);
    fillStrategyList("strategyCoordinate", strategies.coordination_options);
}

function showDecisionRecommendations(result) {
    setVisible("decisionsEmpty", false);
    setVisible("decisionsContent", true);

    var container = element("decisionList");
    clearElement(container);

    for (var index = 0; index < result.decision_recommendations.length; index++) {
        var recommendation = result.decision_recommendations[index];

        var card = document.createElement("article");
        card.className = "decision-card";

        var title = document.createElement("h3");
        title.textContent = recommendation.title;
        card.appendChild(title);

        var detail = document.createElement("p");
        detail.textContent = recommendation.detail;
        card.appendChild(detail);

        container.appendChild(card);
    }

    var coordinationList = element("coordinationList");
    clearElement(coordinationList);

    if (result.coordination_candidates.length === 0) {
        coordinationList.appendChild(createFactorItem(
            "No lower-pressure candidate was found",
            "No other hospital currently shows lower predicted overload risk, lower ICU occupancy and lower bed occupancy at the same time."
        ));
    } else {
        for (var candidateIndex = 0; candidateIndex < result.coordination_candidates.length; candidateIndex++) {
            var candidate = result.coordination_candidates[candidateIndex];
            coordinationList.appendChild(createFactorItem(
                candidate.hospital_label + " - " + candidate.note,
                "Predicted status " + candidate.capacity_status +
                ", predicted overload risk " + formatNumber(candidate.overload_risk_percent, 1) +
                "%, ICU occupancy " + formatNumber(candidate.icu_occupancy_percent, 1) +
                "%, bed occupancy " + formatNumber(candidate.bed_occupancy_percent, 1) + "%."
            ));
        }
    }

    setText("coordinationNote", result.coordination_note);
}


// ============================================================================
// SECTION 9: REQUEST AND DISPLAY ALLOCATION PLAN
// Sends the reserve and the objective weights to /api/allocate.
// ============================================================================

function handleAllocationSubmit(submitEvent) {
    submitEvent.preventDefault();

    if (!appState.ready || appState.pending.allocation) {
        return;
    }

    clearValidationErrors("allocationForm");
    var errors = [];
    var reserve = {
        icu_beds: readWholeNumberField("icuReserve", "Emergency ICU beds available", 0, errors),
        ventilators: readWholeNumberField("ventilatorReserve", "Emergency ventilators available", 0, errors),
        staff: readWholeNumberField("staffReserve", "Emergency staff units available", 0, errors)
    };

    var weights = {
        patient_safety: readNumericField("weightSafety", "Patient Safety weight", 0, null, errors),
        overload_relief: readNumericField("weightOverload", "Overload Relief weight", 0, null, errors),
        patient_demand: readNumericField("weightDemand", "Patient Demand weight", 0, null, errors),
        incident_proximity: readNumericField("weightProximity", "Incident Proximity weight", 0, null, errors)
    };

    var hospitalValue = element(crisisFields.hospital).value;
    if (!hospitalValue) {
        addValidationError(crisisFields.hospital, "Please choose a hospital in the crisis form first.", errors);
    }

    var useScenario = element("useCurrentScenario").checked;
    var snapshot = null;

    if (useScenario) {
        var formData = readCrisisForm();
        if (formData.errors.length > 0) {
            for (var index = 0; index < formData.errors.length; index++) {
                errors.push(formData.errors[index]);
            }
        } else {
            snapshot = formData.snapshot;
        }
    }

    if (errors.length > 0) {
        showListMessage("allocationErrorBox", "Please correct these fields", errors);
        focusFirstInvalid("allocationForm");
        return;
    }
    setVisible("allocationErrorBox", false);

    var requestBody = {
        selected_hospital_id: Number(hospitalValue),
        reserve: reserve,
        weights: weights,
        use_current_scenario: useScenario,
        snapshot: snapshot
    };

    var requestTicket = beginRequest("allocation");
    appState.pending.allocation = true;
    setButtonLoading("buildAllocationButton", true, "Build Allocation Plan");
    refreshWorkflowControls();

    requestApi("/api/allocate", "POST", requestBody, requestTicket.signal).then(function (result) {
        if (!requestIsCurrent("allocation", requestTicket)) {
            return null;
        }
        appState.allocationResult = result;
        appState.hasAllocation = true;
        appState.allocationStale = false;
        appState.showAllAllocationRows = false;
        showAllocationResult(result);
        setVisible("allocationStaleNotice", false);
        updateNavigationState();
        refreshWorkflowControls();
        showView("allocation");
        return result;
    }).catch(function (error) {
        if (!isAbortError(error) && requestIsCurrent("allocation", requestTicket)) {
            showListMessage("allocationErrorBox", "The allocation plan could not be built", [error.message]);
        }
    }).then(function () {
        if (finishRequest("allocation", requestTicket)) {
            appState.pending.allocation = false;
            setButtonLoading("buildAllocationButton", false, "Build Allocation Plan");
            refreshWorkflowControls();
        }
    });
}

function showAllocationResult(result) {
    setVisible("allocationEmpty", false);
    setVisible("allocationContent", true);

    setText("totalIcuAllocated", String(result.total_allocated.icu_beds) + " of " + String(result.reserve_entered.icu_beds));
    setText("remainingIcu", String(result.remaining_reserve.icu_beds) + " ICU beds still unused");

    setText("totalVentAllocated", String(result.total_allocated.ventilators) + " of " + String(result.reserve_entered.ventilators));
    setText("remainingVent", String(result.remaining_reserve.ventilators) + " ventilators still unused");

    setText("totalStaffAllocated", String(result.total_allocated.staff) + " of " + String(result.reserve_entered.staff));
    setText("remainingStaff", String(result.remaining_reserve.staff) + " staff units still unused");

    setText("allocationHospitalCount", String(result.hospital_count));

    // Methodology notes.
    var warningsList = element("allocationWarningsList");
    clearElement(warningsList);
    for (var index = 0; index < result.methodology_warnings.length; index++) {
        var warningItem = document.createElement("li");
        warningItem.textContent = result.methodology_warnings[index];
        warningsList.appendChild(warningItem);
    }

    setText("allocMethodName", result.method);
    setText("allocMethodExplanation", result.method_explanation);
    setText("allocPriorityFormula", result.priority_formula);

    var weightParts = [];
    weightParts.push("Patient Safety " + formatNumber(result.normalized_weights.patient_safety, 3));
    weightParts.push("Overload Relief " + formatNumber(result.normalized_weights.overload_relief, 3));
    weightParts.push("Patient Demand " + formatNumber(result.normalized_weights.patient_demand, 3));
    weightParts.push("Incident Proximity " + formatNumber(result.normalized_weights.incident_proximity, 3));
    setText("allocWeightsNote", weightParts.join("   |   "));

    // Selected hospital summary.
    if (result.selected_hospital_summary) {
        var summary = result.selected_hospital_summary;
        setText("selectedHospitalSummary", summary.hospital_label + " is ranked " + summary.rank + " of " +
            result.hospital_count + " with a priority score of " + formatNumber(summary.priority_score, 2) +
            ". Predicted status " + summary.capacity_status + ", predicted overload risk " +
            formatNumber(summary.overload_risk_percent, 1) + "%. Values used: " + summary.record_source +
            " from " + summary.record_timestamp + ". Reserve received: " + summary.icu_allocated +
            " ICU beds, " + summary.ventilators_allocated + " ventilators, " + summary.staff_allocated + " staff units.");
    } else {
        setText("selectedHospitalSummary", "The selected hospital was not found in the allocation result.");
    }

    showAllocationTable(result);
}

function showAllocationTable(result) {
    var tableBody = element("allocationTableBody");
    var toggleButton = element("toggleAllocationRows");
    clearElement(tableBody);

    // Only the highest priority hospitals are shown first, so the view stays calm.
    var visibleCount = result.rows.length;
    if (!appState.showAllAllocationRows && result.rows.length > 10) {
        visibleCount = 10;
    }

    setVisible("toggleAllocationRows", result.rows.length > 10);
    if (visibleCount < result.rows.length) {
        setText("allocationTableNote", "Showing the top " + visibleCount + " of " + result.rows.length +
            " hospitals, ranked by priority score.");
        setText("toggleAllocationRows", "Show all " + result.rows.length + " hospitals");
        toggleButton.setAttribute("aria-expanded", "false");
    } else {
        setText("allocationTableNote", "Showing all " + result.rows.length + " hospitals, ranked by priority score.");
        if (result.rows.length > 10) {
            setText("toggleAllocationRows", "Show top 10 only");
            toggleButton.setAttribute("aria-expanded", "true");
        }
    }

    for (var index = 0; index < visibleCount; index++) {
        var row = result.rows[index];
        var isSelected = Number(row.hospital_id) === Number(result.selected_hospital_id);

        var tableRow = document.createElement("tr");
        if (isSelected) {
            tableRow.className = "row-selected";
        }

        var cellValues = [
            String(row.rank),
            row.hospital_label,
            formatNumber(row.priority_score, 2),
            row.capacity_status,
            formatNumber(row.overload_risk_percent, 1),
            String(row.predicted_icu_beds),
            String(row.icu_allocated),
            String(row.predicted_ventilators),
            String(row.ventilators_allocated),
            String(row.predicted_staff),
            String(row.staff_allocated)
        ];

        for (var cellIndex = 0; cellIndex < cellValues.length; cellIndex++) {
            var cell = document.createElement("td");

            // The status cell also carries a text badge, never colour alone.
            if (cellIndex === 3) {
                var badge = document.createElement("span");
                badge.className = "status-badge " + statusClassName(row.capacity_status);
                badge.textContent = row.capacity_status;
                cell.appendChild(badge);
            } else {
                cell.textContent = cellValues[cellIndex];
            }

            tableRow.appendChild(cell);
        }

        // A small button opens one extra detail row for this hospital.
        var actionCell = document.createElement("td");
        var detailButton = document.createElement("button");
        detailButton.type = "button";
        detailButton.className = "link-button";
        detailButton.textContent = "Show";
        detailButton.setAttribute("aria-expanded", "false");
        actionCell.appendChild(detailButton);
        tableRow.appendChild(actionCell);

        tableBody.appendChild(tableRow);

        var detailRow = document.createElement("tr");
        detailRow.className = "detail-panel hidden";
        detailRow.id = "allocation-detail-" + index;
        detailButton.setAttribute("aria-controls", detailRow.id);
        detailButton.setAttribute("aria-label", "Show details for " + row.hospital_label);

        var detailCell = document.createElement("td");
        detailCell.setAttribute("colspan", "12");
        detailCell.textContent = "Values used: " + row.record_source + " from " + row.record_timestamp +
            ". Predicted patients in the next 2 hours: " + row.predicted_patients +
            ". Bed occupancy " + formatNumber(row.bed_occupancy_percent, 1) +
            "%, ICU occupancy " + formatNumber(row.icu_occupancy_percent, 1) +
            "%, equipment usage " + formatNumber(row.equipment_usage_percent, 1) +
            "%, distance from incident " + formatNumber(row.incident_distance_km, 1) +
            " km. Classification confidence " + formatNumber(row.capacity_confidence_percent, 1) +
            "%. Objective components: patient safety " + formatNumber(row.components.patient_safety, 3) +
            ", overload relief " + formatNumber(row.components.overload_relief, 3) +
            ", patient demand " + formatNumber(row.components.patient_demand, 3) +
            ", incident proximity " + formatNumber(row.components.incident_proximity, 3) + ".";

        detailRow.appendChild(detailCell);
        tableBody.appendChild(detailRow);

        attachDetailToggle(detailButton, detailRow, row.hospital_label);
    }
}

// Switch between the short table and the full list of hospitals.
function toggleAllocationRows() {
    if (!appState.allocationResult) {
        return;
    }
    appState.showAllAllocationRows = !appState.showAllAllocationRows;
    showAllocationTable(appState.allocationResult);
}

// Connect one detail button to its own hidden row.
function attachDetailToggle(detailButton, detailRow, hospitalLabel) {
    detailButton.addEventListener("click", function () {
        if (detailRow.classList.contains("hidden")) {
            detailRow.classList.remove("hidden");
            detailButton.textContent = "Hide";
            detailButton.setAttribute("aria-expanded", "true");
            detailButton.setAttribute("aria-label", "Hide details for " + hospitalLabel);
        } else {
            detailRow.classList.add("hidden");
            detailButton.textContent = "Show";
            detailButton.setAttribute("aria-expanded", "false");
            detailButton.setAttribute("aria-label", "Show details for " + hospitalLabel);
        }
    });
}


// ============================================================================
// SECTION 10: LOAD AND DISPLAY HISTORY
// Reads /api/history and shows weekly dataset trends for one hospital.
// ============================================================================

function loadHistory(hospitalId) {
    var requestTicket = beginRequest("history");
    return requestApi("/api/history/" + hospitalId, "GET", null, requestTicket.signal).then(function (history) {
        if (!requestIsCurrent("history", requestTicket) ||
                String(element(crisisFields.hospital).value) !== String(hospitalId)) {
            return null;
        }
        appState.historyResult = history;
        showHistory(history);
        clearAppStatus("history");
        return history;
    }).catch(function (error) {
        if (isAbortError(error) || !requestIsCurrent("history", requestTicket)) {
            return null;
        }
        throw error;
    }).then(function (history) {
        finishRequest("history", requestTicket);
        return history;
    }, function (error) {
        finishRequest("history", requestTicket);
        throw error;
    });
}

function showHistory(history) {
    setText("historyHospitalLabel", history.hospital_label);

    if (history.weekly_labels.length === 0) {
        setVisible("historyEmpty", true);
        setVisible("historyContent", false);
        clearElement(element("historyDataTableBody"));
        destroyChart("historyRisk");
        destroyChart("historyResource");
        return;
    }

    setVisible("historyEmpty", false);
    setVisible("historyContent", true);

    setTrendText("trendOverload", history.trends.overload_risk);
    setTrendText("trendBed", history.trends.bed_occupancy);
    setTrendText("trendIcu", history.trends.icu_occupancy);

    setText("historyRecordCount", String(history.summary.record_count));
    setText("historyMinRisk", formatNumber(history.summary.min_overload_risk_percent, 1) + "%");
    setText("historyAvgRisk", formatNumber(history.summary.avg_overload_risk_percent, 1) + "%");
    setText("historyMaxRisk", formatNumber(history.summary.max_overload_risk_percent, 1) + "%");
    setText("historyHighRiskShare", formatNumber(history.summary.high_risk_percent, 1) + "%");

    setText("trendThresholdNote", "Trend directions come from a straight line fitted to the weekly averages. " +
        "A weekly change larger than " + history.trend_threshold + " of the 0 to 1 rate is called Worsening, " +
        "a change smaller than minus " + history.trend_threshold + " is called Improving, and everything between " +
        "them is called Stable. Records used: " + history.summary.record_count + " between " +
        history.summary.first_record + " and " + history.summary.last_record + ".");

    populateHistoryDataTable(history);
    if (appState.currentView === "resilience") {
        updateHistoryCharts(history);
    }
}

function setTrendText(elementId, trend) {
    var target = element(elementId);
    if (!target) {
        return;
    }

    if (trend.slope_per_week === null) {
        target.textContent = trend.direction;
    } else {
        target.textContent = trend.direction + " (" + formatNumber(trend.slope_per_week, 5) + " per week)";
    }

    target.className = "stat-value small " + trendClassName(trend.direction);
}


// ============================================================================
// SECTION 11: CREATE AND UPDATE CHARTS
// Old Chart.js instances are destroyed before a new chart is created.
// ============================================================================

function appendDataTableRow(tableBody, values) {
    var row = document.createElement("tr");
    for (var index = 0; index < values.length; index++) {
        var cell = document.createElement(index === 0 ? "th" : "td");
        if (index === 0) {
            cell.setAttribute("scope", "row");
        }
        cell.textContent = String(values[index]);
        row.appendChild(cell);
    }
    tableBody.appendChild(row);
}

function populateResourceDataTable(result) {
    var tableBody = element("resourceDataTableBody");
    clearElement(tableBody);
    var predictions = result.predictions;
    appendDataTableRow(tableBody, ["Patients in next 2 hours", predictions.patients_next_2h.value]);
    appendDataTableRow(tableBody, ["ICU beds", predictions.icu_beds.value]);
    appendDataTableRow(tableBody, ["Ventilators", predictions.ventilators.value]);
    appendDataTableRow(tableBody, ["Staff units", predictions.staff.value]);
}

function populateHistoryDataTable(history) {
    var tableBody = element("historyDataTableBody");
    clearElement(tableBody);
    for (var index = 0; index < history.weekly_labels.length; index++) {
        appendDataTableRow(tableBody, [
            history.weekly_labels[index],
            history.weekly_values.overload_risk_percent[index],
            history.weekly_values.bed_occupancy_percent[index],
            history.weekly_values.icu_occupancy_percent[index],
            history.weekly_values.required_icu_beds[index],
            history.weekly_values.required_ventilators[index],
            history.weekly_values.required_staff[index]
        ]);
    }
}

function setChartFallback(canvasIds, noticeId, detailsId, messageText, shouldShowFallback) {
    for (var index = 0; index < canvasIds.length; index++) {
        var canvas = element(canvasIds[index]);
        if (canvas && canvas.parentNode) {
            canvas.parentNode.classList.toggle("hidden", shouldShowFallback);
        }
    }
    setText(noticeId, messageText);
    setVisible(noticeId, shouldShowFallback);
    var details = element(detailsId);
    if (details && shouldShowFallback) {
        details.open = true;
    }
}

function connectChartLibraryLoader() {
    var chartScript = element("chartJsScript");
    if (!chartScript) {
        return;
    }
    chartScript.addEventListener("load", function () {
        if (appState.currentView === "results" && appState.predictionResult) {
            updateResourceChart(appState.predictionResult);
        }
        if (appState.currentView === "resilience" && appState.historyResult) {
            updateHistoryCharts(appState.historyResult);
        }
    });
    chartScript.addEventListener("error", function () {
        if (appState.predictionResult) {
            setChartFallback(["resourceChart"], "resourceChartNotice", "resourceDataDetails",
                "The visual chart library could not be loaded. The same prediction values are shown in the table below.", true);
        }
        if (appState.historyResult) {
            setChartFallback(["historyRiskChart", "historyResourceChart"], "historyChartNotice", "historyDataDetails",
                "The visual chart library could not be loaded. The same weekly dataset values are shown in the table below.", true);
        }
    });
}

function chartAnimationEnabled() {
    return !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

function destroyChart(chartName) {
    if (appState.charts[chartName]) {
        appState.charts[chartName].destroy();
        appState.charts[chartName] = null;
    }
}

function updateResourceChart(result) {
    destroyChart("resource");

    if (typeof window.Chart !== "function") {
        setChartFallback(["resourceChart"], "resourceChartNotice", "resourceDataDetails",
            "The visual chart is unavailable. The same prediction values are shown in the table below.", true);
        return;
    }

    try {
        var context = element("resourceChart").getContext("2d");
        var predictions = result.predictions;

        appState.charts.resource = new window.Chart(context, {
        type: "bar",
        data: {
            labels: ["Patients (2h)", "ICU beds", "Ventilators", "Staff units"],
            datasets: [{
                label: "Predicted requirement",
                data: [
                    predictions.patients_next_2h.value,
                    predictions.icu_beds.value,
                    predictions.ventilators.value,
                    predictions.staff.value
                ],
                backgroundColor: ["#1c3d5f", "#12a0b0", "#0f7f8c", "#4a7fa5"],
                borderRadius: 6
            }]
        },
        options: {
            animation: chartAnimationEnabled(),
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: { display: true, text: "Model prediction for " + result.hospital_label }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: "Estimated units" } }
            }
        }
        });
        setChartFallback(["resourceChart"], "resourceChartNotice", "resourceDataDetails", "", false);
    } catch (error) {
        destroyChart("resource");
        setChartFallback(["resourceChart"], "resourceChartNotice", "resourceDataDetails",
            "The visual chart could not be rendered. The same prediction values are shown in the table below.", true);
    }
}

function updateHistoryCharts(history) {
    destroyChart("historyRisk");
    destroyChart("historyResource");

    if (typeof window.Chart !== "function") {
        setChartFallback(["historyRiskChart", "historyResourceChart"], "historyChartNotice", "historyDataDetails",
            "The visual charts are unavailable. The same weekly dataset values are shown in the table below.", true);
        return;
    }

    try {
    var riskContext = element("historyRiskChart").getContext("2d");
    appState.charts.historyRisk = new window.Chart(riskContext, {
        type: "line",
        data: {
            labels: history.weekly_labels,
            datasets: [
                {
                    label: "Overload risk (%)",
                    data: history.weekly_values.overload_risk_percent,
                    borderColor: "#b1281f",
                    backgroundColor: "rgba(177, 40, 31, 0.12)",
                    tension: 0.25
                },
                {
                    label: "Bed occupancy (%)",
                    data: history.weekly_values.bed_occupancy_percent,
                    borderColor: "#1c3d5f",
                    backgroundColor: "rgba(28, 61, 95, 0.12)",
                    tension: 0.25
                },
                {
                    label: "ICU occupancy (%)",
                    data: history.weekly_values.icu_occupancy_percent,
                    borderColor: "#12a0b0",
                    backgroundColor: "rgba(18, 160, 176, 0.12)",
                    tension: 0.25
                }
            ]
        },
        options: {
            animation: chartAnimationEnabled(),
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: "Dataset time-series trends - weekly averages" }
            },
            scales: {
                y: { beginAtZero: true, max: 100, title: { display: true, text: "Percent" } },
                x: { title: { display: true, text: "Week beginning" } }
            }
        }
    });

    var resourceContext = element("historyResourceChart").getContext("2d");
    appState.charts.historyResource = new window.Chart(resourceContext, {
        type: "line",
        data: {
            labels: history.weekly_labels,
            datasets: [
                {
                    label: "ICU beds required",
                    data: history.weekly_values.required_icu_beds,
                    borderColor: "#0f7f8c",
                    backgroundColor: "rgba(15, 127, 140, 0.12)",
                    tension: 0.25
                },
                {
                    label: "Ventilators required",
                    data: history.weekly_values.required_ventilators,
                    borderColor: "#835000",
                    backgroundColor: "rgba(131, 80, 0, 0.12)",
                    tension: 0.25
                },
                {
                    label: "Staff required",
                    data: history.weekly_values.required_staff,
                    borderColor: "#1c7a4b",
                    backgroundColor: "rgba(28, 122, 75, 0.12)",
                    tension: 0.25
                }
            ]
        },
        options: {
            animation: chartAnimationEnabled(),
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: "Dataset time-series trends - weekly averages" }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: "Recorded units" } },
                x: { title: { display: true, text: "Week beginning" } }
            }
        }
    });
        setChartFallback(["historyRiskChart", "historyResourceChart"], "historyChartNotice", "historyDataDetails", "", false);
    } catch (error) {
        destroyChart("historyRisk");
        destroyChart("historyResource");
        setChartFallback(["historyRiskChart", "historyResourceChart"], "historyChartNotice", "historyDataDetails",
            "The visual charts could not be rendered. The same weekly dataset values are shown in the table below.", true);
    }
}


// ============================================================================
// SECTION 12: EXPORT ALLOCATION CSV
// Builds a CSV file in the browser from the latest allocation result.
// ============================================================================

// Put quotation marks around one value so commas cannot break the CSV file.
function csvCell(value) {
    var text = String(value);
    // Spreadsheet applications may execute formula-leading text even when quoted.
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) {
        text = "'" + text;
    }
    text = text.split('"').join('""');
    return '"' + text + '"';
}

function downloadAllocationCsv() {
    var result = appState.allocationResult;
    if (!result) {
        showListMessage("allocationErrorBox", "Nothing to download yet", ["Build an allocation plan first."]);
        return;
    }

    var lines = [];
    var headers = [
        "rank", "hospital", "priority_score", "capacity_status", "overload_risk_percent",
        "predicted_patients_next_2h", "predicted_icu_beds", "predicted_ventilators", "predicted_staff",
        "icu_reserve_allocated", "ventilators_reserve_allocated", "staff_reserve_allocated",
        "values_used", "record_timestamp"
    ];
    lines.push(headers.join(","));

    for (var index = 0; index < result.rows.length; index++) {
        var row = result.rows[index];
        var cells = [
            csvCell(row.rank),
            csvCell(row.hospital_label),
            csvCell(row.priority_score),
            csvCell(row.capacity_status),
            csvCell(row.overload_risk_percent),
            csvCell(row.predicted_patients),
            csvCell(row.predicted_icu_beds),
            csvCell(row.predicted_ventilators),
            csvCell(row.predicted_staff),
            csvCell(row.icu_allocated),
            csvCell(row.ventilators_allocated),
            csvCell(row.staff_allocated),
            csvCell(row.record_source),
            csvCell(row.record_timestamp)
        ];
        lines.push(cells.join(","));
    }

    lines.push("");
    lines.push(csvCell("Method") + "," + csvCell(result.method));
    lines.push(csvCell("Reserve entered - ICU beds") + "," + csvCell(result.reserve_entered.icu_beds));
    lines.push(csvCell("Reserve entered - ventilators") + "," + csvCell(result.reserve_entered.ventilators));
    lines.push(csvCell("Reserve entered - staff units") + "," + csvCell(result.reserve_entered.staff));
    lines.push(csvCell("Total allocated - ICU beds") + "," + csvCell(result.total_allocated.icu_beds));
    lines.push(csvCell("Total allocated - ventilators") + "," + csvCell(result.total_allocated.ventilators));
    lines.push(csvCell("Total allocated - staff units") + "," + csvCell(result.total_allocated.staff));
    lines.push(csvCell("Remaining - ICU beds") + "," + csvCell(result.remaining_reserve.icu_beds));
    lines.push(csvCell("Remaining - ventilators") + "," + csvCell(result.remaining_reserve.ventilators));
    lines.push(csvCell("Remaining - staff units") + "," + csvCell(result.remaining_reserve.staff));

    var fileContent = lines.join("\n");
    var fileBlob = new Blob([fileContent], { type: "text/csv;charset=utf-8;" });
    var fileUrl = URL.createObjectURL(fileBlob);

    var downloadLink = document.createElement("a");
    downloadLink.href = fileUrl;
    downloadLink.download = "allocation_report.csv";
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(fileUrl);
}


// ============================================================================
// SECTION 13: LOADING, ERROR, AND SUCCESS STATES
// Small functions that switch buttons and message boxes.
// ============================================================================

function setButtonLoading(buttonId, isLoading, normalText) {
    var button = element(buttonId);
    if (!button) {
        return;
    }

    if (isLoading) {
        button.disabled = true;
        button.classList.add("is-loading");
        var loadingLabels = {
            analyzeButton: "Analyzing crisis",
            loadLatestButton: "Loading latest record",
            buildAllocationButton: "Building allocation plan",
            chatSendButton: "Sending question"
        };
        button.textContent = loadingLabels[buttonId] || "Working";
    } else {
        button.classList.remove("is-loading");
        button.textContent = normalText;
        refreshWorkflowControls();
    }

    var busyContainers = {
        analyzeButton: "crisisForm",
        loadLatestButton: "crisisForm",
        buildAllocationButton: "allocationForm",
        chatSendButton: "chatForm"
    };
    var busyContainer = element(busyContainers[buttonId]);
    if (busyContainer) {
        busyContainer.setAttribute("aria-busy", isLoading ? "true" : "false");
    }
}

function showListMessage(boxId, titleText, messages) {
    var box = element(boxId);
    if (!box) {
        return;
    }

    clearElement(box);

    var title = document.createElement("strong");
    title.textContent = titleText;
    box.appendChild(title);

    var list = document.createElement("ul");
    for (var index = 0; index < messages.length; index++) {
        var listItem = document.createElement("li");
        listItem.textContent = messages[index];
        list.appendChild(listItem);
    }
    box.appendChild(list);

    box.classList.remove("hidden");
}

function showStartupError(messageText) {
    appState.ready = false;
    setAppStatus("startup", "error", "The application is not ready", [messageText]);
    refreshWorkflowControls();
}


// ============================================================================
// SECTION 14: EVENT LISTENERS AND STARTUP
// Connects the buttons and runs the first data load when the page opens.
// ============================================================================

function clearCrisisRecordFields() {
    Object.keys(crisisFields).forEach(function (fieldName) {
        if (fieldName === "hospital") {
            return;
        }
        var field = element(crisisFields[fieldName]);
        if (field) {
            field.value = "";
        }
    });
    clearValidationErrors("crisisForm");
}

function handleHospitalChange() {
    var hospitalId = element(crisisFields.hospital).value;
    if (!hospitalId) {
        return;
    }

    appState.scenarioRevision += 1;
    appState.scenarioBasis = "Loading the selected hospital's latest dataset record";
    setText("topbarHospital", selectedHospitalLabel());
    invalidatePrediction("The selected hospital changed after this result was calculated.");
    invalidateAllocation("The selected hospital changed after this report was built.");
    clearCrisisRecordFields();
    setText("latestRecordNote", "Loading the selected hospital's latest dataset record.");
    updateScenarioStrip();

    loadLatestRecord(hospitalId, "hospital-change").catch(function (error) {
        if (!isAbortError(error)) {
            setText("latestRecordNote", "No latest dataset record is loaded for the selected hospital.");
            showListMessage("formErrorBox", "The latest dataset record could not be loaded", [error.message]);
        }
    });

    loadHistory(hospitalId).catch(function (error) {
        if (!isAbortError(error)) {
            setVisible("historyContent", false);
            setVisible("historyEmpty", true);
            setText("historyHospitalLabel", "this hospital");
            setAppStatus("history", "warning", "The dataset trends could not be loaded", [error.message]);
        }
    });
}

function handleLoadLatestClick() {
    if (!appState.ready || appState.pending.latest) {
        return;
    }
    var hospitalId = element(crisisFields.hospital).value;
    if (!hospitalId) {
        showListMessage("formErrorBox", "Please choose a hospital", ["A hospital must be selected first."]);
        return;
    }

    markScenarioEdited("The latest dataset record was loaded after this result was calculated.");
    appState.scenarioBasis = "Loading the latest dataset record";
    updateScenarioStrip();

    loadLatestRecord(hospitalId, "manual").then(function () {
        setVisible("formErrorBox", false);
    }).catch(function (error) {
        if (!isAbortError(error)) {
            showListMessage("formErrorBox", "The latest dataset record could not be loaded", [error.message]);
        }
    });
}

function handleCrisisFormInput(inputEvent) {
    var target = inputEvent.target;
    if (!target || target.id === crisisFields.hospital) {
        return;
    }
    // A manual edit wins over an in-flight prefill. Cancel before recording the
    // edited scenario so an older latest-record response cannot replace it.
    cancelPendingLatestRecordForManualEdit();
    clearFieldError(target);
    setVisible("formErrorBox", false);
    markScenarioEdited("A Step 1 value changed after this result was calculated.");
}

function handleAllocationFormInput(inputEvent) {
    if (inputEvent.target) {
        clearFieldError(inputEvent.target);
    }
    setVisible("allocationErrorBox", false);
    invalidateAllocation("The reserve, priorities or scenario setting changed after this report was built.");
}

// Keep the small number next to every weight slider up to date.
function connectWeightSlider(sliderId, outputId) {
    var slider = element(sliderId);
    var output = element(outputId);
    if (!slider || !output) {
        return;
    }

    slider.addEventListener("input", function () {
        output.textContent = slider.value;
    });
}

function connectEventListeners() {
    element("crisisForm").addEventListener("submit", handleCrisisSubmit);
    element("crisisForm").addEventListener("input", handleCrisisFormInput);
    element("allocationForm").addEventListener("submit", handleAllocationSubmit);
    element("allocationForm").addEventListener("input", handleAllocationFormInput);
    element("loadLatestButton").addEventListener("click", handleLoadLatestClick);
    element("downloadAllocationButton").addEventListener("click", downloadAllocationCsv);
    element("toggleAllocationRows").addEventListener("click", toggleAllocationRows);
    element(crisisFields.hospital).addEventListener("change", handleHospitalChange);

    connectWeightSlider("weightSafety", "weightSafetyValue");
    connectWeightSlider("weightOverload", "weightOverloadValue");
    connectWeightSlider("weightDemand", "weightDemandValue");
    connectWeightSlider("weightProximity", "weightProximityValue");

    connectNavigation();
    connectChat();
}

function startApplication() {
    appState.ready = false;
    connectEventListeners();
    connectChartLibraryLoader();
    updateNavigationState();
    refreshWorkflowControls();

    // The overview is the opening view, so its sidebar button starts active.
    showView("overview", { updateHash: false, focus: false });
    var requestedView = viewNameFromHash();

    loadStatus().then(function (status) {
        if (!status.ready) {
            return null;
        }
        return loadOptions();
    }).then(function (options) {
        if (!options) {
            return null;
        }
        if (options.hospitals.length === 0) {
            throw new Error("The dataset does not contain a hospital to select.");
        }

        // The first hospital is selected so the page is never empty.
        var firstHospitalId = options.hospitals[0].id;
        element(crisisFields.hospital).value = String(firstHospitalId);

        return loadLatestRecord(firstHospitalId, "bootstrap").then(function (record) {
            if (!record) {
                throw new Error("The first hospital record could not be loaded.");
            }

            appState.ready = true;
            clearAppStatus();
            refreshWorkflowControls();
            updateScenarioStrip();
            startChatConversation();

            if (requestedView && requestedView !== "overview") {
                if (isViewUnlocked(requestedView)) {
                    showView(requestedView, { updateHash: false, focus: true });
                } else {
                    explainLockedView(requestedView);
                }
            } else {
                replaceViewHash("overview");
            }

            loadHistory(firstHospitalId).catch(function (error) {
                if (!isAbortError(error)) {
                    setAppStatus("history", "warning", "The dataset trends could not be loaded", [error.message]);
                }
            });
            return record;
        });
    }).catch(function (error) {
        showStartupError(error.message);
    });
}


// ============================================================================
// SECTION 15: SIDEBAR NAVIGATION AND VIEW SWITCHING
// Only one view is shown at a time, so each screen has one clear purpose.
// ============================================================================

// Views that stay locked until the matching result exists.
var viewRequirements = {
    results: "prediction",
    strategies: "prediction",
    decisions: "prediction",
    allocation: "allocation"
};

// Show one view and mark its sidebar button as the active one.
function viewNameFromHash() {
    var hashValue = window.location.hash.replace(/^#/, "");
    if (hashValue.indexOf("view-") === 0) {
        hashValue = hashValue.slice(5);
    }
    return element("view-" + hashValue) ? hashValue : null;
}

function replaceViewHash(viewName) {
    if (window.history && window.history.replaceState) {
        window.history.replaceState({ view: viewName }, "", "#" + viewName);
    } else {
        window.location.replace("#" + viewName);
    }
}

function pushViewHash(viewName) {
    if (window.location.hash === "#" + viewName) {
        return;
    }
    if (window.history && window.history.pushState) {
        window.history.pushState({ view: viewName }, "", "#" + viewName);
    } else {
        window.location.hash = viewName;
    }
}

function focusViewHeading(targetView) {
    var heading = targetView ? targetView.querySelector("h2") : null;
    if (!heading) {
        element("viewHost").focus();
        return;
    }
    heading.setAttribute("tabindex", "-1");
    try {
        heading.focus({ preventScroll: true });
    } catch (error) {
        heading.focus();
    }
}

function showView(viewName, viewOptions) {
    var options = viewOptions || {};
    var targetView = element("view-" + viewName);
    if (!targetView) {
        return;
    }

    // A locked view cannot be opened before its result exists.
    if (!isViewUnlocked(viewName)) {
        return;
    }

    var allViews = document.querySelectorAll(".view");
    for (var index = 0; index < allViews.length; index++) {
        allViews[index].classList.remove("is-active");
    }
    targetView.classList.add("is-active");

    var allButtons = document.querySelectorAll(".nav-item");
    for (var buttonIndex = 0; buttonIndex < allButtons.length; buttonIndex++) {
        var button = allButtons[buttonIndex];
        if (button.getAttribute("data-view") === viewName) {
            button.classList.add("is-active");
            button.setAttribute("aria-current", "page");
        } else {
            button.classList.remove("is-active");
            button.removeAttribute("aria-current");
        }
    }

    appState.currentView = viewName;
    setText("topbarTitle", targetView.getAttribute("data-title"));

    closeSidebar(false);
    if (options.updateHash !== false) {
        pushViewHash(viewName);
    }
    scrollViewToTop();
    if (viewName === "results" && appState.predictionResult) {
        updateResourceChart(appState.predictionResult);
    }
    if (viewName === "resilience" && appState.historyResult) {
        updateHistoryCharts(appState.historyResult);
    }
    if (options.focus !== false) {
        focusViewHeading(targetView);
    }
}

// Report whether one view already has the result it needs.
function isViewUnlocked(viewName) {
    var requirement = viewRequirements[viewName];
    if (!requirement) {
        return true;
    }
    if (requirement === "prediction") {
        return appState.hasPrediction;
    }
    if (requirement === "allocation") {
        return appState.hasAllocation;
    }
    return true;
}

// Update the locked or ready label of every sidebar button.
function updateNavigationState() {
    var allButtons = document.querySelectorAll(".nav-item");

    for (var index = 0; index < allButtons.length; index++) {
        var button = allButtons[index];
        var viewName = button.getAttribute("data-view");
        var stateLabel = button.querySelector(".nav-state");

        if (!viewRequirements[viewName]) {
            continue;
        }

        var isStale = (viewRequirements[viewName] === "prediction" && appState.predictionStale) ||
            (viewRequirements[viewName] === "allocation" && appState.allocationStale);

        if (isViewUnlocked(viewName)) {
            button.classList.remove("is-locked");
            button.classList.toggle("is-ready", !isStale);
            button.classList.toggle("is-stale", isStale);
            button.removeAttribute("aria-disabled");
            if (stateLabel) {
                stateLabel.textContent = isStale ? "Stale" : "Ready";
            }
        } else {
            button.classList.add("is-locked");
            button.classList.remove("is-ready");
            button.classList.remove("is-stale");
            button.setAttribute("aria-disabled", "true");
            if (stateLabel) {
                stateLabel.textContent = "Locked";
            }
        }
    }
}

// Explain in the interface why a locked section cannot be opened yet.
function explainLockedView(viewName) {
    if (viewRequirements[viewName] === "prediction") {
        showListMessage("formErrorBox", "This section needs a prediction first",
            ["Run “Analyze Crisis and Build Recovery Plan” and this section will open automatically."]);
        showView("analysis");
    } else if (viewRequirements[viewName] === "allocation") {
        showListMessage("allocationErrorBox", "This section needs an allocation plan first",
            ["Enter your available reserve and select “Build Allocation Plan”."]);
        showView("reserve");
    }
}

function compactSidebarIsActive() {
    return window.matchMedia && window.matchMedia("(max-width: 1080px)").matches;
}

function setMainInert(isInert) {
    var main = element("appMain");
    if (!main) {
        return;
    }
    if ("inert" in main) {
        main.inert = isInert;
    } else if (isInert) {
        main.setAttribute("aria-hidden", "true");
    } else {
        main.removeAttribute("aria-hidden");
    }
}

function openSidebar() {
    if (!compactSidebarIsActive()) {
        return;
    }
    appState.drawerReturnFocus = document.activeElement;
    element("sidebar").classList.add("is-open");
    element("sidebar").setAttribute("aria-hidden", "false");
    element("sidebarBackdrop").classList.add("is-open");
    element("sidebarBackdrop").setAttribute("aria-hidden", "false");
    element("menuButton").setAttribute("aria-expanded", "true");
    document.body.classList.add("drawer-open");
    setMainInert(true);
    element("sidebarClose").focus();
}

function closeSidebar(restoreFocus) {
    var wasOpen = element("sidebar").classList.contains("is-open");
    element("sidebar").classList.remove("is-open");
    element("sidebarBackdrop").classList.remove("is-open");
    element("sidebarBackdrop").setAttribute("aria-hidden", "true");
    element("menuButton").setAttribute("aria-expanded", "false");
    document.body.classList.remove("drawer-open");
    setMainInert(false);

    if (compactSidebarIsActive()) {
        element("sidebar").setAttribute("aria-hidden", "true");
    } else {
        element("sidebar").removeAttribute("aria-hidden");
    }

    if (wasOpen && restoreFocus !== false && appState.drawerReturnFocus &&
            typeof appState.drawerReturnFocus.focus === "function") {
        appState.drawerReturnFocus.focus();
    }
    appState.drawerReturnFocus = null;
}

function syncSidebarAccessibility() {
    if (compactSidebarIsActive()) {
        if (!element("sidebar").classList.contains("is-open")) {
            element("sidebar").setAttribute("aria-hidden", "true");
        }
    } else {
        closeSidebar(false);
        element("sidebar").removeAttribute("aria-hidden");
    }
}

function handleDrawerKeydown(keyEvent) {
    if (!element("sidebar").classList.contains("is-open")) {
        return;
    }
    if (keyEvent.key === "Escape") {
        keyEvent.preventDefault();
        closeSidebar(true);
        return;
    }
    if (keyEvent.key !== "Tab") {
        return;
    }

    var focusable = element("sidebar").querySelectorAll(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])"
    );
    if (focusable.length === 0) {
        keyEvent.preventDefault();
        return;
    }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (keyEvent.shiftKey && document.activeElement === first) {
        keyEvent.preventDefault();
        last.focus();
    } else if (!keyEvent.shiftKey && document.activeElement === last) {
        keyEvent.preventDefault();
        first.focus();
    }
}

function handleLocationNavigation() {
    if (!appState.ready) {
        return;
    }
    var viewName = viewNameFromHash();
    if (!viewName || viewName === appState.currentView) {
        return;
    }
    if (isViewUnlocked(viewName)) {
        showView(viewName, { updateHash: false, focus: true });
    } else {
        explainLockedView(viewName);
    }
}

// Connect every sidebar button and every in-page shortcut button.
function connectNavigation() {
    var allButtons = document.querySelectorAll(".nav-item");
    for (var index = 0; index < allButtons.length; index++) {
        connectNavButton(allButtons[index]);
    }

    var shortcutButtons = document.querySelectorAll("[data-goto]");
    for (var shortcutIndex = 0; shortcutIndex < shortcutButtons.length; shortcutIndex++) {
        connectShortcutButton(shortcutButtons[shortcutIndex]);
    }

    element("menuButton").addEventListener("click", openSidebar);
    element("sidebarClose").addEventListener("click", function () { closeSidebar(true); });
    element("sidebarBackdrop").addEventListener("click", function () { closeSidebar(true); });
    document.addEventListener("keydown", handleDrawerKeydown);
    window.addEventListener("resize", syncSidebarAccessibility);
    window.addEventListener("popstate", handleLocationNavigation);
    window.addEventListener("hashchange", handleLocationNavigation);
    syncSidebarAccessibility();
}

function connectNavButton(button) {
    button.addEventListener("click", function () {
        var viewName = button.getAttribute("data-view");
        if (isViewUnlocked(viewName)) {
            showView(viewName);
        } else {
            explainLockedView(viewName);
        }
    });
}

function connectShortcutButton(button) {
    button.addEventListener("click", function () {
        var viewName = button.getAttribute("data-goto");
        if (isViewUnlocked(viewName)) {
            showView(viewName);
        } else {
            explainLockedView(viewName);
        }
    });
}


// ============================================================================
// SECTION 16: CHAT ASSISTANT
// Sends the question to /api/chat and renders only the server answer.
// ============================================================================

// Add one message bubble to the conversation log.
function addChatMessage(roleName, answerText, detailLines, sourceText) {
    var log = element("chatLog");

    var row = document.createElement("div");
    row.className = "chat-message " + (roleName === "you" ? "is-user" : "is-bot");

    var bubble = document.createElement("div");
    bubble.className = "chat-bubble";

    var roleLabel = document.createElement("span");
    roleLabel.className = "chat-role";
    roleLabel.textContent = roleName === "you" ? "You" : "Planner assistant";
    bubble.appendChild(roleLabel);

    var answer = document.createElement("p");
    answer.className = "chat-answer";
    answer.textContent = answerText;
    bubble.appendChild(answer);

    if (detailLines && detailLines.length > 0) {
        var list = document.createElement("ul");
        list.className = "chat-details";
        for (var index = 0; index < detailLines.length; index++) {
            var listItem = document.createElement("li");
            listItem.textContent = detailLines[index];
            list.appendChild(listItem);
        }
        bubble.appendChild(list);
    }

    if (sourceText) {
        var source = document.createElement("span");
        source.className = "chat-source";
        source.textContent = sourceText;
        bubble.appendChild(source);
    }

    row.appendChild(bubble);
    log.appendChild(row);

    // The newest message is always the visible one.
    log.scrollTop = log.scrollHeight;
}

// Draw the clickable example questions under the conversation.
function showChatSuggestions(suggestionList) {
    var holder = element("chatSuggestions");
    clearElement(holder);

    for (var index = 0; index < suggestionList.length; index++) {
        holder.appendChild(createChatChip(suggestionList[index]));
    }
    refreshWorkflowControls();
}

function createChatChip(questionText) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chat-chip";
    chip.textContent = questionText;
    chip.disabled = !appState.ready || appState.pending.chat;

    chip.addEventListener("click", function () {
        element("chatInput").value = questionText;
        sendChatQuestion(questionText);
    });

    return chip;
}

// Write the first assistant message when the page opens.
function startChatConversation() {
    if (appState.chatStarted) {
        return;
    }
    appState.chatStarted = true;
    clearElement(element("chatLog"));
    var assistedMode = aiAssistedModeAvailable(appState.aiInfo);
    var degradedMode = Boolean(appState.aiInfo && appState.aiInfo.enabled === true && !assistedMode);
    var greetingText = "Hello. I answer questions about this planner using fixed rules and the same verified data it shows elsewhere.";
    var modeDetailText = "Rule-based mode understands the topics listed in the chips below.";
    var sourceText = "Language-model wording is off; answers are generated by fixed rules.";

    if (assistedMode) {
        greetingText = "Hello. I answer questions from this planner's verified data, with optional language-model help for wording.";
        modeDetailText = "The language model may reword an answer, but the listed figures still come from the planner.";
        sourceText = "Assisted wording is enabled; it does not create or change the underlying numbers.";
    } else if (degradedMode) {
        greetingText = "Hello. Language-model assistance is enabled but unavailable, so I am using the planner's fixed-rule fallback.";
        modeDetailText = appState.aiInfo.configuration_valid ?
            "The language-model service is unavailable; fixed rules keep the verified dataset and model values usable." :
            "The language-model configuration is incomplete or invalid; fixed rules keep the verified dataset and model values usable.";
        sourceText = "Fixed-rule fallback is active; no language-model wording is being used.";
    }
    addChatMessage(
        "assistant",
        greetingText,
        [
            "Ask about the dataset, the model scores, or the allocation method.",
            "Name a hospital to get its record, its prediction or its dataset trends, for example 'predict hospital 12'.",
            modeDetailText
        ],
        sourceText
    );

    showChatSuggestions([
        "What is in this dataset?",
        "How accurate is the model?",
        "Which hospital is under the most pressure?",
        "What does the resilience index mean?",
        "How does the allocation work?",
        "What are the limitations?"
    ]);
}

function handleChatSubmit(submitEvent) {
    submitEvent.preventDefault();
    if (!appState.ready || appState.pending.chat) {
        return;
    }
    var questionText = element("chatInput").value.trim();
    sendChatQuestion(questionText);
}

function sendChatQuestion(questionText) {
    if (questionText === "" || !appState.ready || appState.pending.chat) {
        return;
    }

    addChatMessage("you", questionText, [], "");
    element("chatInput").value = "";
    var requestTicket = beginRequest("chat");
    appState.pending.chat = true;
    setButtonLoading("chatSendButton", true, "Send");
    refreshWorkflowControls();

    var requestBody = { message: questionText };
    var hospitalValue = element(crisisFields.hospital).value;
    if (hospitalValue) {
        requestBody.selected_hospital_id = Number(hospitalValue);
    }

    requestApi("/api/chat", "POST", requestBody, requestTicket.signal).then(function (reply) {
        if (!requestIsCurrent("chat", requestTicket)) {
            return null;
        }
        var sourceText = reply.source_note;
        if (reply.ai_error) {
            sourceText = sourceText + " The language model was not used: " + reply.ai_error;
        }
        addChatMessage("assistant", reply.answer, reply.details, sourceText);
        if (reply.suggestions && reply.suggestions.length > 0) {
            showChatSuggestions(reply.suggestions);
        }
    }).catch(function (error) {
        if (!isAbortError(error) && requestIsCurrent("chat", requestTicket)) {
            addChatMessage("assistant", "I could not answer that question.", [error.message], "");
        }
    }).then(function () {
        if (finishRequest("chat", requestTicket)) {
            appState.pending.chat = false;
            setButtonLoading("chatSendButton", false, "Send");
            refreshWorkflowControls();
            if (appState.currentView === "assistant") {
                element("chatInput").focus();
            }
        }
    });
}

function connectChat() {
    element("chatForm").addEventListener("submit", handleChatSubmit);
}


document.addEventListener("DOMContentLoaded", startApplication);
