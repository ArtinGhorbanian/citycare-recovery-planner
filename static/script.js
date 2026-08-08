// ============================================================================
// SECTION 1: APPLICATION STATE AND DOM ELEMENTS
// Keeps the latest real API results and short links to the page elements.
// ============================================================================

var appState = {
    ready: false,
    options: null,
    status: null,
    predictionResult: null,
    allocationResult: null,
    historyResult: null,
    currentView: "overview",
    hasPrediction: false,
    hasAllocation: false,
    showAllAllocationRows: false,
    aiInfo: null,
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
    if (target) {
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

// Fill one select element with real option values from the dataset.
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
    window.scrollTo({ top: 0, behavior: "smooth" });
}


// ============================================================================
// SECTION 3: API REQUEST HELPER
// One small function that talks to the Flask API and reports clear errors.
// ============================================================================

function requestApi(path, method, bodyObject) {
    var settings = { method: method, headers: { "Content-Type": "application/json" } };
    if (bodyObject) {
        settings.body = JSON.stringify(bodyObject);
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
        appState.ready = status.ready === true;

        if (!appState.ready) {
            var message = "The dataset or the models could not be prepared.";
            if (status.startup_error) {
                message = message + " Details: " + status.startup_error;
            }
            showStartupError(message);
            return status;
        }

        setVisible("appStatusBanner", false);
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
        setText("assistantModeNote", "Rule-based mode: answers are written from fixed rules and real dataset values.");
        return;
    }

    if (aiInfo.enabled) {
        setText("aiStatusText", "Switched on, using the model " + aiInfo.model + ". " + aiInfo.note);
        setText("assistantModeNote", "Assisted mode: " + aiInfo.model +
            " rewords the answers, and the exact values stay listed under each one.");
    } else {
        setText("aiStatusText", "Switched off. Every answer and briefing is written by fixed rules from the real values. " +
            "Set AI_ENABLED=true in the .env file to switch it on.");
        setText("assistantModeNote", "Rule-based mode: answers are written from fixed rules and real dataset values.");
    }
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
    cornerCell.textContent = "Real status";
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

        // The hospital dropdown uses the real hospital identifiers.
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
// Fills the crisis form with the latest real dataset record of one hospital.
// ============================================================================

function loadLatestRecord(hospitalId) {
    return requestApi("/api/hospital/" + hospitalId + "/latest", "GET", null).then(function (record) {
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

        return record;
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
        errors.push(labelText + " is required.");
        return null;
    }

    var numberValue = Number(rawValue);
    if (isNaN(numberValue) || !isFinite(numberValue)) {
        errors.push(labelText + " must be a normal number.");
        return null;
    }

    if (numberValue < minimumValue) {
        errors.push(labelText + " cannot be below " + minimumValue + ".");
        return null;
    }

    if (maximumValue !== null && numberValue > maximumValue) {
        errors.push(labelText + " cannot be above " + maximumValue + ".");
        return null;
    }

    return numberValue;
}

// Build the snapshot object that both /api/predict and /api/allocate accept.
function readCrisisForm() {
    var errors = [];
    var snapshot = {};

    var hospitalValue = element(crisisFields.hospital).value;
    if (!hospitalValue) {
        errors.push("Please choose a hospital.");
    } else {
        snapshot.hospital_id = Number(hospitalValue);
    }

    var timestampValue = element(crisisFields.timestamp).value;
    if (!timestampValue) {
        errors.push("Please choose a date and time.");
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
            errors.push(labelText + " is required.");
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

    var formData = readCrisisForm();
    if (formData.errors.length > 0) {
        showListMessage("formErrorBox", "Please correct these fields", formData.errors);
        return;
    }
    setVisible("formErrorBox", false);

    setButtonLoading("analyzeButton", true, "Analyze Crisis and Build Recovery Plan");

    requestApi("/api/predict", "POST", formData.snapshot).then(function (result) {
        appState.predictionResult = result;
        appState.hasPrediction = true;
        showPredictionResult(result);
        showRecoveryStrategies(result);
        showDecisionRecommendations(result);
        updateNavigationState();
        showView("results");
        loadBriefing(formData.snapshot);
    }).catch(function (error) {
        showListMessage("formErrorBox", "The analysis could not be completed", [error.message]);
    }).then(function () {
        setButtonLoading("analyzeButton", false, "Analyze Crisis and Build Recovery Plan");
    });
}

function showPredictionResult(result) {
    setVisible("resultsEmpty", false);
    setVisible("resultsContent", true);

    var predictions = result.predictions;

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
    updateResourceChart(result);
}

// Ask the server for the written briefing that belongs to this exact situation.
function loadBriefing(snapshot) {
    setText("briefingSummary", "Preparing the briefing...");
    clearElement(element("briefingRecommendations"));
    setText("briefingSourceNote", "");

    requestApi("/api/briefing", "POST", snapshot).then(function (briefing) {
        showBriefing(briefing);
    }).catch(function (error) {
        setText("briefingSummary", "The briefing could not be created: " + error.message);
        setText("briefingSourceNote", "The prediction values above are not affected by this.");
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
    setText("similarFilterNote", "Real dataset rows selected with this filter: " + similarCases.filter_used + ".");

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

    var errors = [];
    var reserve = {
        icu_beds: readNumericField("icuReserve", "Emergency ICU beds available", 0, null, errors),
        ventilators: readNumericField("ventilatorReserve", "Emergency ventilators available", 0, null, errors),
        staff: readNumericField("staffReserve", "Emergency staff units available", 0, null, errors)
    };

    var weights = {
        patient_safety: readNumericField("weightSafety", "Patient Safety weight", 0, null, errors),
        overload_relief: readNumericField("weightOverload", "Overload Relief weight", 0, null, errors),
        patient_demand: readNumericField("weightDemand", "Patient Demand weight", 0, null, errors),
        incident_proximity: readNumericField("weightProximity", "Incident Proximity weight", 0, null, errors)
    };

    var hospitalValue = element(crisisFields.hospital).value;
    if (!hospitalValue) {
        errors.push("Please choose a hospital in the crisis form first.");
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

    setButtonLoading("buildAllocationButton", true, "Build Allocation Plan");

    requestApi("/api/allocate", "POST", requestBody).then(function (result) {
        appState.allocationResult = result;
        appState.hasAllocation = true;
        showAllocationResult(result);
        element("downloadAllocationButton").disabled = false;
        updateNavigationState();
        showView("allocation");
    }).catch(function (error) {
        showListMessage("allocationErrorBox", "The allocation plan could not be built", [error.message]);
    }).then(function () {
        setButtonLoading("buildAllocationButton", false, "Build Allocation Plan");
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
    clearElement(tableBody);

    // Only the highest priority hospitals are shown first, so the view stays calm.
    var visibleCount = result.rows.length;
    if (!appState.showAllAllocationRows && result.rows.length > 10) {
        visibleCount = 10;
    }

    if (visibleCount < result.rows.length) {
        setText("allocationTableNote", "Showing the top " + visibleCount + " of " + result.rows.length +
            " hospitals, ranked by priority score.");
        setText("toggleAllocationRows", "Show all " + result.rows.length + " hospitals");
    } else {
        setText("allocationTableNote", "Showing all " + result.rows.length + " hospitals, ranked by priority score.");
        setText("toggleAllocationRows", "Show top 10 only");
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
        actionCell.appendChild(detailButton);
        tableRow.appendChild(actionCell);

        tableBody.appendChild(tableRow);

        var detailRow = document.createElement("tr");
        detailRow.className = "detail-panel hidden";

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

        attachDetailToggle(detailButton, detailRow);
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
function attachDetailToggle(detailButton, detailRow) {
    detailButton.addEventListener("click", function () {
        if (detailRow.classList.contains("hidden")) {
            detailRow.classList.remove("hidden");
            detailButton.textContent = "Hide";
        } else {
            detailRow.classList.add("hidden");
            detailButton.textContent = "Show";
        }
    });
}


// ============================================================================
// SECTION 10: LOAD AND DISPLAY HISTORY
// Reads /api/history and shows the real weekly trends of one hospital.
// ============================================================================

function loadHistory(hospitalId) {
    return requestApi("/api/history/" + hospitalId, "GET", null).then(function (history) {
        appState.historyResult = history;
        showHistory(history);
        return history;
    });
}

function showHistory(history) {
    setText("historyHospitalLabel", history.hospital_label);

    if (history.weekly_labels.length === 0) {
        setVisible("historyEmpty", true);
        setVisible("historyContent", false);
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

    updateHistoryCharts(history);
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

function destroyChart(chartName) {
    if (appState.charts[chartName]) {
        appState.charts[chartName].destroy();
        appState.charts[chartName] = null;
    }
}

function updateResourceChart(result) {
    destroyChart("resource");

    var context = element("resourceChart").getContext("2d");
    var predictions = result.predictions;

    appState.charts.resource = new Chart(context, {
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
}

function updateHistoryCharts(history) {
    destroyChart("historyRisk");
    destroyChart("historyResource");

    var riskContext = element("historyRiskChart").getContext("2d");
    appState.charts.historyRisk = new Chart(riskContext, {
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
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: "Real historical dataset trends - weekly averages" }
            },
            scales: {
                y: { beginAtZero: true, max: 100, title: { display: true, text: "Percent" } },
                x: { title: { display: true, text: "Week beginning" } }
            }
        }
    });

    var resourceContext = element("historyResourceChart").getContext("2d");
    appState.charts.historyResource = new Chart(resourceContext, {
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
                    borderColor: "#a86a06",
                    backgroundColor: "rgba(168, 106, 6, 0.12)",
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
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: "Real historical dataset trends - weekly averages" }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: "Recorded units" } },
                x: { title: { display: true, text: "Week beginning" } }
            }
        }
    });
}


// ============================================================================
// SECTION 12: EXPORT ALLOCATION CSV
// Builds a CSV file in the browser from the latest real allocation result.
// ============================================================================

// Put quotation marks around one value so commas cannot break the CSV file.
function csvCell(value) {
    var text = String(value);
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
        button.textContent = "Working";
    } else {
        button.disabled = false;
        button.classList.remove("is-loading");
        button.textContent = normalText;
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
    showListMessage("appStatusBanner", "The application is not ready", [messageText]);

    // Every model action is switched off while the startup problem is not solved.
    element("analyzeButton").disabled = true;
    element("loadLatestButton").disabled = true;
    element("buildAllocationButton").disabled = true;
    element("chatSendButton").disabled = true;
}


// ============================================================================
// SECTION 14: EVENT LISTENERS AND STARTUP
// Connects the buttons and runs the first data load when the page opens.
// ============================================================================

function handleHospitalChange() {
    var hospitalId = element(crisisFields.hospital).value;
    if (!hospitalId) {
        return;
    }

    loadLatestRecord(hospitalId).catch(function (error) {
        showListMessage("formErrorBox", "The latest dataset record could not be loaded", [error.message]);
    });

    loadHistory(hospitalId).catch(function (error) {
        setVisible("historyContent", false);
        setVisible("historyEmpty", true);
        setText("historyHospitalLabel", "this hospital");
        showListMessage("appStatusBanner", "The history could not be loaded", [error.message]);
    });
}

function handleLoadLatestClick() {
    var hospitalId = element(crisisFields.hospital).value;
    if (!hospitalId) {
        showListMessage("formErrorBox", "Please choose a hospital", ["A hospital must be selected first."]);
        return;
    }

    setButtonLoading("loadLatestButton", true, "Load Latest Dataset Record");

    loadLatestRecord(hospitalId).then(function () {
        setVisible("formErrorBox", false);
    }).catch(function (error) {
        showListMessage("formErrorBox", "The latest dataset record could not be loaded", [error.message]);
    }).then(function () {
        setButtonLoading("loadLatestButton", false, "Load Latest Dataset Record");
    });
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
    element("allocationForm").addEventListener("submit", handleAllocationSubmit);
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
    connectEventListeners();
    updateNavigationState();
    startChatConversation();

    // The overview is the opening view, so its sidebar button starts active.
    showView("overview");

    loadStatus().then(function (status) {
        if (!status.ready) {
            return null;
        }
        return loadOptions();
    }).then(function (options) {
        if (!options || options.hospitals.length === 0) {
            return null;
        }

        // The first hospital is selected so the page is never empty.
        var firstHospitalId = options.hospitals[0].id;
        element(crisisFields.hospital).value = String(firstHospitalId);

        return loadLatestRecord(firstHospitalId).then(function () {
            return loadHistory(firstHospitalId);
        });
    }).catch(function (error) {
        showStartupError(error.message);
    });
}


// ============================================================================
// SECTION 15: SIDEBAR NAVIGATION AND VIEW SWITCHING
// Only one view is shown at a time, so each screen has one clear purpose.
// ============================================================================

// Views that stay locked until the matching real result exists.
var viewRequirements = {
    results: "prediction",
    strategies: "prediction",
    decisions: "prediction",
    allocation: "allocation"
};

// Show one view and mark its sidebar button as the active one.
function showView(viewName) {
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

    closeSidebar();
    scrollViewToTop();
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

        if (isViewUnlocked(viewName)) {
            button.classList.remove("is-locked");
            button.classList.add("is-ready");
            button.removeAttribute("aria-disabled");
            if (stateLabel) {
                stateLabel.textContent = "Ready";
            }
        } else {
            button.classList.add("is-locked");
            button.classList.remove("is-ready");
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

function openSidebar() {
    element("sidebar").classList.add("is-open");
    element("sidebarBackdrop").classList.add("is-open");
    element("menuButton").setAttribute("aria-expanded", "true");
}

function closeSidebar() {
    element("sidebar").classList.remove("is-open");
    element("sidebarBackdrop").classList.remove("is-open");
    element("menuButton").setAttribute("aria-expanded", "false");
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
    element("sidebarClose").addEventListener("click", closeSidebar);
    element("sidebarBackdrop").addEventListener("click", closeSidebar);
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
}

function createChatChip(questionText) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chat-chip";
    chip.textContent = questionText;

    chip.addEventListener("click", function () {
        element("chatInput").value = questionText;
        sendChatQuestion(questionText);
    });

    return chip;
}

// Write the first assistant message when the page opens.
function startChatConversation() {
    addChatMessage(
        "assistant",
        "Hello. I answer questions about this planner using the same real numbers it shows everywhere else.",
        [
            "Ask about the dataset, the model scores, or the allocation method.",
            "Name a hospital to get its record, its prediction or its history, for example 'predict hospital 12'.",
            "I use fixed rules, so I only understand the topics listed in the chips below."
        ],
        "I am not a language model and I never invent a number."
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
    var questionText = element("chatInput").value.trim();
    sendChatQuestion(questionText);
}

function sendChatQuestion(questionText) {
    if (questionText === "") {
        return;
    }

    addChatMessage("you", questionText, [], "");
    element("chatInput").value = "";
    setButtonLoading("chatSendButton", true, "Send");

    var requestBody = { message: questionText };
    var hospitalValue = element(crisisFields.hospital).value;
    if (hospitalValue) {
        requestBody.selected_hospital_id = Number(hospitalValue);
    }

    requestApi("/api/chat", "POST", requestBody).then(function (reply) {
        var sourceText = reply.source_note;
        if (reply.ai_error) {
            sourceText = sourceText + " The language model was not used: " + reply.ai_error;
        }
        addChatMessage("assistant", reply.answer, reply.details, sourceText);
        if (reply.suggestions && reply.suggestions.length > 0) {
            showChatSuggestions(reply.suggestions);
        }
    }).catch(function (error) {
        addChatMessage("assistant", "I could not answer that question.", [error.message], "");
    }).then(function () {
        setButtonLoading("chatSendButton", false, "Send");
        element("chatInput").focus();
    });
}

function connectChat() {
    element("chatForm").addEventListener("submit", handleChatSubmit);
}


document.addEventListener("DOMContentLoaded", startApplication);
