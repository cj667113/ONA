let ruleType = "dnat";
let dashboardButton = document.getElementById("dashboard-btn");
let dnatButton = document.getElementById("dnat-btn");
let snatButton = document.getElementById("snat-btn");
let backupsButton = document.getElementById("backups-btn");
let dnatTable = document.getElementById("dnat-table");
let snatTable = document.getElementById("snat-table");
let dashboardView = document.getElementById("dashboard-view");
let dnatView = document.getElementById("dnat-view");
let snatView = document.getElementById("snat-view");
let backupsView = document.getElementById("backups-view");
let tempDeleteButton = document.getElementById("temp-delete-btn");
let tempDropDown = document.getElementById("temp-dropdown");
let tempDropDownSNATProtocol = document.getElementById("temp-dropdown-snat-protocol");
let tempDropDownSNAT = document.getElementById("temp-dropdown-2");
let dashboardPollTimer = null;
let dashboardHistory = [];
let dashboardRangeSeconds = 3600;
let dashboardChartResizeTimer = null;
let dashboardChartResizeListenerAttached = false;
let snatInterfaceOptions = [];
let submitToastTimer = null;

console.log("V1.6.1 Loaded");

function showSubmitSuccess(message) {
  var toast = document.getElementById("submit-toast");
  if (!toast) {
    return;
  }
  toast.textContent = message || "Submit successful";
  toast.classList.add("is-visible");
  clearTimeout(submitToastTimer);
  submitToastTimer = setTimeout(function () {
    toast.classList.remove("is-visible");
  }, 3000);
}

function updateDropDowns() {
  //console.log("Updating Dropdowns");
  var dropdowns = document.getElementsByClassName('select');
  for (var obj of dropdowns) {
    if (obj.className === 'select') {
      var options = obj.children;
      //console.log("Object Dropdown" + obj);
      for (let child of options) {
        if (obj.getAttribute('value') === child.getAttribute('value')) {
          child.setAttribute("selected", "");
        }
      }
    }
  }
}

//Drop-down menu modifier
$(document).ready(function () {
  console.log(" - Document Ready - ");

  //Default the correct drop-down selection for protocol
  updateDropDowns();
  loadVnicState();
  loadBackupState();
  setupDashboardCharts();
  loadDashboardHistory();
  startDashboardStream();

  //Update select element value when selection changes
  $(document).on('change', '.dropper', function () {
    //console.log("Dropdown changing.");
    //alert($(this).val());
    $(this).attr("value", $(this).val());
    //console.log($(this).val());
  });

})

function changeMenu(menu) {
  var sections = {
    dashboard: { button: dashboardButton, view: dashboardView },
    dnat: { button: dnatButton, view: dnatView },
    snat: { button: snatButton, view: snatView },
    backups: { button: backupsButton, view: backupsView },
  };

  if (!sections[menu]) {
    console.log("Something went wrong!");
    return;
  }

  for (let key of Object.keys(sections)) {
    var section = sections[key];
    if (!section.button || !section.view) {
      continue;
    }
    if (key === menu) {
      section.button.classList.add("is-active");
      section.view.classList.remove("d-none");
    } else {
      section.button.classList.remove("is-active");
      section.view.classList.add("d-none");
    }
  }

  if (menu === "dnat" || menu === "snat") {
    ruleType = menu;
  }
  if (menu === "dashboard") {
    setTimeout(renderDashboardCharts, 0);
  }
}


function add_row_dnat() {
  //console.log("add dnat row");
  var table = dnatTable.getElementsByTagName('tbody')[0];

  var cloned_delete_dnat = tempDeleteButton.cloneNode(true);
  cloned_delete_dnat.id = "";
  cloned_delete_dnat.className = "";

  var cloned_dropdown_dnat = tempDropDown.cloneNode(true);
  cloned_dropdown_dnat.id = "dropdown-dnat";
  cloned_dropdown_dnat.className = "select dropper";

  try {
    var loc = table.rows.length;
    //console.log(loc);
  } catch (error) {
    var loc = 0;
  }
  var table_id = loc - 1;
  var row = table.insertRow();
  row.id = "dnat_row_" + table_id;
  var cell0 = row.insertCell(0);
  var cell1 = row.insertCell(1);
  var cell2 = row.insertCell(2);
  var cell3 = row.insertCell(3);
  var cell4 = row.insertCell(4);
  var cell5 = row.insertCell(5);
  cell0.innerHTML = "<div>" + table_id + "</div>";
  cell1.appendChild(cloned_dropdown_dnat);
  cell2.innerHTML = "<div contenteditable>-</div>";
  cell3.innerHTML = "<div contenteditable>-</div>";
  cell4.innerHTML = "<div contenteditable>-</div>";
  cell5.appendChild(cloned_delete_dnat);
  organizeRules();
}

function add_row_snat() {
  //console.log("add snat row");
  var table = snatTable.getElementsByTagName('tbody')[0];
  var cloned_delete_snat = tempDeleteButton.cloneNode(true);
  cloned_delete_snat.id = "";
  cloned_delete_snat.className = "";

  var cloned_dropdown_snat = tempDropDownSNATProtocol.cloneNode(true);
  cloned_dropdown_snat.id = "dropdown-snat";
  cloned_dropdown_snat.className = "select dropper";

  var cloned_dropdown_snat2 = tempDropDownSNAT.cloneNode(true);
  cloned_dropdown_snat2.id = "dropdown-snat2";
  cloned_dropdown_snat2.className = "select dropper";

  try {
    var loc = table.rows.length;
  } catch (error) {
    var loc = 0;
  }
  var table_id = loc - 1;
  var row = table.insertRow();
  row.id = "snat_row_" + table_id;
  var cell0 = row.insertCell(0);
  var cell1 = row.insertCell(1);
  var cell2 = row.insertCell(2);
  var cell3 = row.insertCell(3);
  var cell4 = row.insertCell(4);
  var cell5 = row.insertCell(5);
  cell0.innerHTML = "<div>" + table_id + "</div>";
  cell1.appendChild(cloned_dropdown_snat);
  cell2.appendChild(cloned_dropdown_snat2);
  cell3.innerHTML = "<div contenteditable>Null</div>";
  cell4.appendChild(snatInterfaceControl(""));
  cell5.appendChild(cloned_delete_snat);
  organizeRules();
}

function addRule() {
  if (ruleType === "dnat") {
    //console.log("Calling add_row_dnat");
    add_row_dnat();
  }
  else if (ruleType === "snat") {
    //console.log("Calling add_row_snat");
    add_row_snat();
  }
  else { console.log("Something bad happened.") };
}

function organizeRules() {
  var selected_Table;
  if (ruleType === "dnat") {
    selected_Table = dnatTable.getElementsByTagName('tbody')[0];
  }
  else if (ruleType === "snat") {
    selected_Table = snatTable.getElementsByTagName('tbody')[0];
  }
  else {
    console.log("Couldn't Identify Table for Organizing.");
  }

  try {
    for (let row = 0; row < selected_Table.rows.length; row++) {
      var tableRow = selected_Table.rows[row];
      tableRow.id = ruleType + "_row_" + row;
      tableRow.cells[0].innerHTML = "<div>" + row + "</div>";
    }
  }
  catch (error) {
    console.log(error);
  }

}

function deleteRule(rule) {
  rule.parentElement.closest('tr').remove();
  organizeRules();
}

function tableToJson() {
  var data_dnat = [];
  var table_dnat = dnatTable.getElementsByTagName('tbody')[0];
  var data_snat = [];
  var table_snat = snatTable.getElementsByTagName('tbody')[0];
  var dict = {};
  var setData;

  for (var i = 0; i < table_dnat.rows.length; i++) {
    var tableRow = table_dnat.rows[i];
    var rowData = [];
    for (var j = 0; j < tableRow.cells.length; j++) {
      if (j === 1) {
        try {
          setData = tableRow.cells[j].querySelector(".select").value;
          rowData.push(setData);
          continue;
        } catch (error) {
          console.error(error);
        }
      }
      setData = tableRow.cells[j].textContent.trim();
      rowData.push(setData);
    }
    data_dnat.push(rowData);
  }
  for (let d = 0; d < data_dnat.length; d++) {
    let predict = {};
    predict["chain"] = "PREROUTING";
    predict["protocol"] = data_dnat[d][1];
    predict["destination_port"] = data_dnat[d][2];
    predict["target"] = "DNAT";
    predict["forward_ip"] = data_dnat[d][3];
    predict["forward_port"] = data_dnat[d][4];
    dict[data_dnat[d][0]] = predict;
  }
  for (var e = 0; e < table_snat.rows.length; e++) {
    var tableRow = table_snat.rows[e];
    var rowData = [];
    for (var f = 0; f < tableRow.cells.length; f++) {
      if (f === 1 || f === 2 || f === 4) {
        try {
          setData = tableRow.cells[f].querySelector(".select").value;
          rowData.push(setData);
          continue;
        } catch (error) {
          console.error(error);
        }
      }
      //console.log("Untrimmed - " + tableRow.cells[f] + " TextContent - " + tableRow.cells[f].textContent);
      //console.log("Element Name: " + tableRow.cells[f].querySelector(".select").nodeName);
      setData = tableRow.cells[f].textContent.trim();
      //console.log("Set Data: " + setData);
      rowData.push(setData);
    }
    data_snat.push(rowData);
  }

  var total_length = data_dnat.length + data_snat.length;
  var d = 0;
  for (let dn = data_dnat.length; dn < total_length; dn++) {
    let predict = {};
    predict["chain"] = "POSTROUTING";
    predict["protocol"] = data_snat[d][1];
    predict["target"] = data_snat[d][2];
    predict["source_ip"] = data_snat[d][3];
    predict["output_interface"] = data_snat[d][4];
    if (table_snat.rows[d] && table_snat.rows[d].dataset.probability) {
      predict["probability"] = table_snat.rows[d].dataset.probability;
    }
    dict[dn] = predict;
    d++;
  }
  return dict;
}
function sendJson() {
  var csrfToken = getCsrfToken();
  var xhr = new XMLHttpRequest();

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        let response = JSON.parse(xhr.responseText);
        renderNatTables(response.dnat_rules || {}, response.snat_rules || {});
      } catch (error) {
        console.error(error);
      }
      showSubmitSuccess();
      return;
    }
    let message = "Unable to submit NAT rules.";
    try {
      let response = JSON.parse(xhr.responseText);
      if (response.error) {
        message = response.error;
      }
    } catch (error) {
      console.error(error);
    }
    alert(message);
  };

  xhr.onerror = () => alert("Unable to submit NAT rules.");
  xhr.open("POST", "/", true);
  xhr.setRequestHeader("Content-Type", "application/json; charset=UTF-8");
  xhr.setRequestHeader("X-CSRFToken", csrfToken);
  var j = tableToJson();
  console.log(j);
  xhr.send(JSON.stringify(j));
}

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]').getAttribute("content");
}

function requestJson(url, method, body) {
  var headers = { "Accept": "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json; charset=UTF-8";
    headers["X-CSRFToken"] = getCsrfToken();
  }

  return fetch(url, {
    method: method,
    headers: headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  }).then(async function (response) {
    var data = {};
    try {
      data = await response.json();
    } catch (error) {
      console.error(error);
    }
    if (!response.ok) {
      throw new Error(data.error || "Request failed.");
    }
    return data;
  });
}

function selectControl(options, selectedValue, extraClass) {
  var select = document.createElement("select");
  select.name = "dropdown";
  select.className = extraClass || "select dropper";
  select.setAttribute("value", selectedValue);
  for (let optionData of options) {
    var option = document.createElement("option");
    option.value = optionData.value;
    option.textContent = optionData.label;
    if (optionData.value === selectedValue) {
      option.selected = true;
    }
    select.appendChild(option);
  }
  return select;
}

function normalizeInterfaceValue(value) {
  var selected = (value || "").trim();
  return selected === "-" || selected === "No interfaces loaded" ? "" : selected;
}

function snatInterfaceControl(selectedValue) {
  var selected = normalizeInterfaceValue(selectedValue);
  var options = snatInterfaceOptions.slice();
  var selectedKnown = options.some(function (option) {
    return option.value === selected;
  });

  if (selected && !selectedKnown) {
    options.unshift({ value: selected, label: selected + " (current)" });
  }
  if (!options.length) {
    options.push({ value: selected, label: selected || "No interfaces loaded" });
  }

  var select = selectControl(options, selected, "select dropper snat-interface-select");
  if (!selected && snatInterfaceOptions.length) {
    select.value = snatInterfaceOptions[0].value;
    select.setAttribute("value", select.value);
  }
  if (!snatInterfaceOptions.length && !selected) {
    select.disabled = true;
  }
  return select;
}

function snatInterfaceCell(selectedValue) {
  var cell = document.createElement("td");
  cell.appendChild(snatInterfaceControl(selectedValue));
  return cell;
}

function editableCell(value) {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  div.contentEditable = "true";
  div.textContent = value;
  cell.appendChild(div);
  return cell;
}

function textCell(value) {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  div.textContent = value;
  cell.appendChild(div);
  return cell;
}

function deleteCell() {
  var cell = document.createElement("td");
  var div = document.createElement("div");
  var button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-outline-danger btn-sm";
  button.textContent = "X";
  button.addEventListener("click", function () {
    deleteRule(button);
  });
  div.appendChild(button);
  cell.appendChild(div);
  return cell;
}

function renderNatTables(dnatRules, snatRules) {
  var dnatBody = dnatTable.getElementsByTagName("tbody")[0];
  var snatBody = snatTable.getElementsByTagName("tbody")[0];
  dnatBody.replaceChildren();
  snatBody.replaceChildren();

  for (let key of sortedObjectKeys(dnatRules)) {
    var rule = dnatRules[key];
    var dnatRow = document.createElement("tr");
    dnatRow.id = "dnat_row_" + key;
    dnatRow.appendChild(textCell(key));

    var protocolCell = document.createElement("td");
    protocolCell.appendChild(selectControl([
      { value: "tcp", label: "TCP" },
      { value: "udp", label: "UDP" },
    ], rule.protocol, "select dropper"));
    dnatRow.appendChild(protocolCell);

    dnatRow.appendChild(editableCell(rule.destination_port));
    dnatRow.appendChild(editableCell(rule.forward_ip));
    dnatRow.appendChild(editableCell(rule.forward_port));
    dnatRow.appendChild(deleteCell());
    dnatBody.appendChild(dnatRow);
  }

  for (let key of sortedObjectKeys(snatRules)) {
    var snatRule = snatRules[key];
    var snatRow = document.createElement("tr");
    snatRow.id = "snat_row_" + key;
    if (snatRule.probability) {
      snatRow.dataset.probability = snatRule.probability;
    }
    snatRow.appendChild(textCell(key));

    var snatProtocolCell = document.createElement("td");
    snatProtocolCell.appendChild(selectControl([
      { value: "all", label: "ALL" },
      { value: "tcp", label: "TCP" },
      { value: "udp", label: "UDP" },
    ], snatRule.protocol, "select dropper"));
    snatRow.appendChild(snatProtocolCell);

    var targetCell = document.createElement("td");
    targetCell.appendChild(selectControl([
      { value: "MASQUERADE", label: "MASQUERADE" },
      { value: "SNAT", label: "SNAT" },
    ], snatRule.target, "select dropper"));
    snatRow.appendChild(targetCell);

    snatRow.appendChild(editableCell(snatRule.source_ip));
    snatRow.appendChild(snatInterfaceCell(snatRule.output_interface));
    snatRow.appendChild(deleteCell());
    snatBody.appendChild(snatRow);
  }
}

function sortedObjectKeys(obj) {
  return Object.keys(obj || {}).sort(function (a, b) {
    var aNum = Number(a);
    var bNum = Number(b);
    if (!Number.isNaN(aNum) && !Number.isNaN(bNum)) {
      return aNum - bNum;
    }
    return a.localeCompare(b);
  });
}

function vnicElement(id) {
  return document.getElementById(id);
}

function addInterfaceOption(options, seen, name, addresses) {
  var normalized = normalizeInterfaceValue(name);
  if (!normalized || seen.has(normalized)) {
    return;
  }
  seen.add(normalized);
  options.push({
    value: normalized,
    label: normalized + (addresses && addresses.length ? " (" + addresses.join(", ") + ")" : ""),
  });
}

function scannedInterfaceOptions(scan) {
  var seen = new Set();
  var options = [];
  for (let item of scan.interfaces || []) {
    if (!item || !item.name) {
      continue;
    }
    if (item.name === "lo") {
      continue;
    }
    addInterfaceOption(options, seen, item.name, item.addresses || []);
  }
  for (let ipInfo of scan.source_ips || []) {
    if (ipInfo.interface === "lo") {
      continue;
    }
    addInterfaceOption(options, seen, ipInfo.interface, []);
  }
  return options;
}

function setSnatInterfaceOptions(scan) {
  snatInterfaceOptions = scannedInterfaceOptions(scan || {});
  refreshSnatInterfaceCells();
}

function populateInterfaceSelect(select, options, selectedValue, placeholderText) {
  var selected = normalizeInterfaceValue(selectedValue);
  var hasSelected = options.some(function (option) {
    return option.value === selected;
  });

  select.replaceChildren();
  if (!selected && options.length) {
    selected = options[0].value;
    hasSelected = true;
  }

  if (selected && !hasSelected) {
    var currentOption = document.createElement("option");
    currentOption.value = selected;
    currentOption.textContent = selected + " (current)";
    currentOption.selected = true;
    select.appendChild(currentOption);
  } else {
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = options.length ? placeholderText : "No interfaces loaded";
    placeholder.selected = !selected;
    select.appendChild(placeholder);
  }

  for (let optionData of options) {
    var option = document.createElement("option");
    option.value = optionData.value;
    option.textContent = optionData.label;
    if (optionData.value === selected) {
      option.selected = true;
    }
    select.appendChild(option);
  }

  select.disabled = !options.length && !selected;
}

function refreshSnatInterfaceCells() {
  if (!snatTable) {
    return;
  }
  var body = snatTable.getElementsByTagName("tbody")[0];
  if (!body) {
    return;
  }

  for (let row of body.rows) {
    if (!row.cells[4]) {
      continue;
    }
    var existingSelect = row.cells[4].querySelector("select");
    var selected = existingSelect ? existingSelect.value : row.cells[4].textContent.trim();
    row.replaceChild(snatInterfaceCell(selected), row.cells[4]);
  }
}

function setVnicStatus(message, isError) {
  var status = vnicElement("vnic-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.className = isError ? "panel-status text-danger" : "panel-status";
}

function shortOcid(value) {
  var text = (value || "").trim();
  if (!text) {
    return "-";
  }
  if (text.length <= 28) {
    return text;
  }
  return text.slice(0, 18) + "..." + text.slice(-8);
}

function copyText(value, button) {
  var text = (value || "").trim();
  if (!text) {
    return;
  }

  function markCopied() {
    var original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(function () {
      button.textContent = original;
    }, 1200);
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(markCopied).catch(function () {
      fallbackCopyText(text, markCopied);
    });
    return;
  }
  fallbackCopyText(text, markCopied);
}

function fallbackCopyText(text, onCopied) {
  var textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  document.body.appendChild(textArea);
  textArea.select();
  try {
    document.execCommand("copy");
    onCopied();
  } catch (error) {
    console.error(error);
  }
  textArea.remove();
}

function vnicIdCell(value) {
  var cell = document.createElement("td");
  var text = (value || "").trim();
  var wrapper = document.createElement("div");
  wrapper.className = "vnic-id-cell";

  var label = document.createElement("span");
  label.className = "vnic-id-text";
  label.textContent = shortOcid(text);
  label.title = text || "-";
  wrapper.appendChild(label);

  if (text) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-primary btn-sm copy-ocid-btn";
    button.textContent = "Copy";
    button.addEventListener("click", function () {
      copyText(text, button);
    });
    wrapper.appendChild(button);
  }

  cell.appendChild(wrapper);
  return cell;
}

function snatPoolPayloadFromForm() {
  var selectedIps = [];
  document.querySelectorAll(".snat-source-checkbox:checked").forEach(function (checkbox) {
    selectedIps.push(checkbox.value);
  });
  return {
    enabled: vnicElement("snat-pool-enabled").checked,
    source_ips: selectedIps,
  };
}

function vnicConfigurationMessage(data, fallbackMessage) {
  var configuration = data.configuration || {};
  var results = configuration.results || [];
  var errors = configuration.errors || [];
  var configured = Number.isFinite(Number(configuration.configured_count))
    ? Number(configuration.configured_count)
    : results.filter(function (item) {
      return item.status === "configured";
    }).length;

  if (errors.length) {
    return configured
      ? "Configured " + formatNumber(configured) + " address(es); " + formatNumber(errors.length) + " need attention."
      : formatNumber(errors.length) + " address(es) still need attention.";
  }
  if (configured) {
    return "Configured " + formatNumber(configured) + " address(es).";
  }
  return fallbackMessage;
}

function renderVnicState(data) {
  var scan = data.scan || {};
  var pool = data.snat_pool || {};
  var capacity = data.capacity || {};
  var selectedIps = new Set(pool.source_ips || []);
  var sourceIps = scan.source_ips || [];
  var vnicList = vnicElement("vnic-list");

  setSnatInterfaceOptions(scan);

  if (!vnicList) {
    return;
  }

  vnicElement("snat-pool-enabled").checked = Boolean(pool.enabled);
  vnicElement("snat-pool-capacity").textContent = formatNumber(capacity.total_available_ports) +
    " ports across " + formatNumber(capacity.source_ip_count || 1) + " source IPs";

  vnicList.replaceChildren();
  if (!sourceIps.length) {
    var emptyRow = document.createElement("tr");
    var emptyCell = document.createElement("td");
    emptyCell.colSpan = 7;
    emptyCell.className = "compact-empty";
    emptyCell.textContent = "No VNIC IPs scanned.";
    emptyRow.appendChild(emptyCell);
    vnicList.appendChild(emptyRow);
    setVnicStatus("No VNIC scan loaded.", false);
    return;
  }

  for (let ipInfo of sourceIps) {
    var row = document.createElement("tr");

    var useCell = document.createElement("td");
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "form-check-input snat-source-checkbox";
    checkbox.value = ipInfo.ip;
    checkbox.checked = selectedIps.has(ipInfo.ip);
    checkbox.disabled = !ipInfo.interface;
    useCell.appendChild(checkbox);
    row.appendChild(useCell);

    var ipCell = document.createElement("td");
    ipCell.textContent = ipInfo.ip + (ipInfo.primary ? " primary" : "");
    row.appendChild(ipCell);

    var vnicCell = vnicIdCell(ipInfo.vnic_id);
    row.appendChild(vnicCell);

    var interfaceCell = document.createElement("td");
    interfaceCell.textContent = ipInfo.interface || "-";
    row.appendChild(interfaceCell);

    var nicCell = document.createElement("td");
    nicCell.textContent = ipInfo.nic_index === undefined ? "-" : ipInfo.nic_index;
    row.appendChild(nicCell);

    var statusCell = document.createElement("td");
    statusCell.textContent = ipInfo.configured ? "Ready" : (ipInfo.interface ? "Needs config" : "No OS interface");
    statusCell.className = ipInfo.configured ? "text-success" : "text-warning";
    row.appendChild(statusCell);

    var subnetCell = document.createElement("td");
    var matchedVnic = (scan.vnics || []).find(function (vnic) {
      return vnic.vnic_id === ipInfo.vnic_id;
    });
    subnetCell.textContent = matchedVnic ? (matchedVnic.subnet_cidr || "-") : "-";
    row.appendChild(subnetCell);

    vnicList.appendChild(row);
  }

  var scannedAt = scan.scanned_at ? formatDate(scan.scanned_at) : "-";
  setVnicStatus("Last scan: " + scannedAt, false);
}

function loadVnicState() {
  if (!vnicElement("vnic-panel")) {
    return;
  }
  requestJson("/api/vnics/status", "GET")
    .then(renderVnicState)
    .catch(function (error) {
      setVnicStatus(error.message, true);
    });
}

function rescanVnics() {
  setVnicStatus("Scanning attached VNICs...", false);
  requestJson("/api/vnics/rescan", "POST", {})
    .then(function (data) {
      renderVnicState(data);
      showSubmitSuccess();
    })
    .catch(function (error) {
      setVnicStatus(error.message, true);
      alert(error.message);
    });
}

function configureVnicSources() {
  setVnicStatus("Scanning and configuring VNICs...", false);
  requestJson("/api/vnics/configure", "POST", {})
    .then(function (data) {
      renderVnicState(data);
      var message = vnicConfigurationMessage(data, "VNICs scanned. No OS changes needed.");
      var hasErrors = Boolean(data.configuration && data.configuration.errors && data.configuration.errors.length);
      setVnicStatus(message, hasErrors);
      loadDashboardStats();
      if (!hasErrors) {
        showSubmitSuccess();
      }
    })
    .catch(function (error) {
      setVnicStatus(error.message, true);
      alert(error.message);
    });
}

function applySnatPool() {
  setVnicStatus("Scanning, configuring, and applying SNAT pool...", false);
  requestJson("/api/vnics/snat-pool", "POST", snatPoolPayloadFromForm())
    .then(function (data) {
      renderVnicState(data);
      renderNatTables(data.dnat_rules || {}, data.snat_rules || {});
      var configMessage = vnicConfigurationMessage(data, "");
      var hasErrors = Boolean(data.configuration && data.configuration.errors && data.configuration.errors.length);
      setVnicStatus(configMessage ? configMessage + " SNAT pool applied." : "SNAT pool applied.", hasErrors);
      loadDashboardStats();
      if (!hasErrors) {
        showSubmitSuccess();
      }
    })
    .catch(function (error) {
      setVnicStatus(error.message, true);
      alert(error.message);
    });
}

function backupElement(id) {
  return document.getElementById(id);
}

function setBackupStatus(message, isError) {
  var status = backupElement("backup-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.className = isError ? "panel-status text-danger" : "panel-status";
}

function backupPolicyFromForm() {
  return {
    auth_method: "instance_principal",
    region: backupElement("backup-region").value.trim(),
    compartment_id: backupElement("backup-compartment").value.trim(),
    namespace: backupElement("backup-namespace").value.trim(),
    bucket: backupElement("backup-bucket").value,
    prefix: backupElement("backup-prefix").value.trim(),
    enabled: backupElement("backup-enabled").checked,
    schedule: backupElement("backup-schedule").value,
    time_utc: backupElement("backup-time").value || "00:00",
    weekday: backupElement("backup-weekday").value,
    retention: backupElement("backup-retention").value || "30",
  };
}

function populateBackupPolicy(policy) {
  backupElement("backup-auth-method").value = "instance_principal";
  backupElement("backup-region").value = policy.region || "";
  backupElement("backup-compartment").value = policy.compartment_id || "";
  backupElement("backup-namespace").value = policy.namespace || "";
  backupElement("backup-prefix").value = policy.prefix || "ona-backups/";
  backupElement("backup-enabled").checked = Boolean(policy.enabled);
  backupElement("backup-schedule").value = policy.schedule || "manual";
  backupElement("backup-time").value = policy.time_utc || "00:00";
  backupElement("backup-weekday").value = policy.weekday || "0";
  backupElement("backup-retention").value = policy.retention || "30";
  selectBackupBucket(policy.bucket || "");
}

function setBucketOptions(buckets, selectedBucket) {
  var bucketSelect = backupElement("backup-bucket");
  if (!bucketSelect) {
    return;
  }
  bucketSelect.replaceChildren();

  var placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = buckets.length ? "Select a bucket" : "No buckets loaded";
  bucketSelect.appendChild(placeholder);

  var hasSelected = false;
  for (let bucket of buckets) {
    var option = document.createElement("option");
    option.value = bucket.name;
    option.textContent = bucket.name;
    if (bucket.name === selectedBucket) {
      option.selected = true;
      hasSelected = true;
    }
    bucketSelect.appendChild(option);
  }

  if (selectedBucket && !hasSelected) {
    var selectedOption = document.createElement("option");
    selectedOption.value = selectedBucket;
    selectedOption.textContent = selectedBucket;
    selectedOption.selected = true;
    bucketSelect.appendChild(selectedOption);
  }
}

function selectBackupBucket(selectedBucket) {
  var bucketSelect = backupElement("backup-bucket");
  if (!bucketSelect) {
    return;
  }
  if (!bucketSelect.options.length) {
    setBucketOptions([], selectedBucket);
    return;
  }

  var hasSelected = false;
  for (let option of bucketSelect.options) {
    if (option.value === selectedBucket) {
      hasSelected = true;
      break;
    }
  }

  if (selectedBucket && !hasSelected) {
    var selectedOption = document.createElement("option");
    selectedOption.value = selectedBucket;
    selectedOption.textContent = selectedBucket;
    bucketSelect.appendChild(selectedOption);
  }
  bucketSelect.value = selectedBucket || "";
}

function renderBackupList(backups) {
  var backupList = backupElement("backup-list");
  if (!backupList) {
    return;
  }
  backupList.replaceChildren();

  if (!backups || backups.length === 0) {
    var emptyRow = document.createElement("tr");
    var emptyCell = document.createElement("td");
    emptyCell.colSpan = 4;
    emptyCell.className = "text-muted";
    emptyCell.textContent = "No backups found for this bucket and prefix.";
    emptyRow.appendChild(emptyCell);
    backupList.appendChild(emptyRow);
    return;
  }

  for (let backup of backups) {
    var row = document.createElement("tr");

    var objectCell = document.createElement("td");
    objectCell.textContent = backup.name;
    row.appendChild(objectCell);

    var sizeCell = document.createElement("td");
    sizeCell.className = "text-end";
    sizeCell.textContent = formatBytes(backup.size);
    row.appendChild(sizeCell);

    var createdCell = document.createElement("td");
    createdCell.textContent = formatDate(backup.time_created || backup.time_modified);
    row.appendChild(createdCell);

    var actionCell = document.createElement("td");
    actionCell.className = "text-end";
    var actions = document.createElement("div");
    actions.className = "backup-actions";

    var restoreButton = document.createElement("button");
    restoreButton.type = "button";
    restoreButton.className = "btn btn-outline-primary btn-sm";
    restoreButton.textContent = "Restore";
    restoreButton.addEventListener("click", function () {
      restoreBackup(backup.name);
    });
    actions.appendChild(restoreButton);

    var deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "btn btn-outline-danger btn-sm";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", function () {
      deleteBackup(backup.name);
    });
    actions.appendChild(deleteButton);

    actionCell.appendChild(actions);
    row.appendChild(actionCell);

    backupList.appendChild(row);
  }
}

function formatBytes(value) {
  var bytes = Number(value || 0);
  if (bytes < 1024) {
    return bytes + " B";
  }
  if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KB";
  }
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  var date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function loadBackupState(options) {
  if (!backupElement("backup-panel")) {
    return Promise.resolve();
  }
  options = options || {};
  setBackupStatus(options.loadingMessage || "Loading backup status...", false);
  return requestJson("/api/backups/status", "GET")
    .then(function (data) {
      if (!options.preservePolicy) {
        populateBackupPolicy(data.policy || {});
      }
      renderBackupList(data.backups || []);
      if (data.error) {
        setBackupStatus(data.error, true);
      } else if (options.successMessage) {
        setBackupStatus(options.successMessage, false);
      } else if (data.policy && data.policy.last_backup_error) {
        setBackupStatus("Last backup failed: " + data.policy.last_backup_error, true);
      } else if (data.policy && data.policy.last_backup_at) {
        setBackupStatus("Last backup: " + formatDate(data.policy.last_backup_at), false);
      } else {
        setBackupStatus("No backup has run yet.", false);
      }
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
    });
}

function refreshBuckets() {
  var policy = backupPolicyFromForm();
  var params = new URLSearchParams({
    auth_method: "instance_principal",
    region: policy.region,
    compartment_id: policy.compartment_id,
    namespace: policy.namespace,
  });
  setBackupStatus("Loading buckets...", false);
  requestJson("/api/oci/buckets?" + params.toString(), "GET")
    .then(function (data) {
      if (data.namespace) {
        backupElement("backup-namespace").value = data.namespace;
      }
      setBucketOptions(data.buckets || [], policy.bucket);
      setBackupStatus("Buckets loaded.", false);
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function saveBackupPolicy() {
  var policy = backupPolicyFromForm();
  setBackupStatus("Saving backup policy...", false);
  requestJson("/api/backups/policy", "POST", policy)
    .then(function (data) {
      populateBackupPolicy(Object.assign({}, data.policy || {}, policy));
      return loadBackupState({
        preservePolicy: true,
        loadingMessage: "Refreshing backups...",
        successMessage: "Backup policy saved.",
      });
    })
    .then(function () {
      showSubmitSuccess();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function runBackupNow() {
  var policy = backupPolicyFromForm();
  setBackupStatus("Saving backup policy...", false);
  requestJson("/api/backups/policy", "POST", policy)
    .then(function (data) {
      populateBackupPolicy(Object.assign({}, data.policy || {}, policy));
      setBackupStatus("Creating backup...", false);
      return requestJson("/api/backups/run", "POST", {});
    })
    .then(function (data) {
      return loadBackupState({
        preservePolicy: true,
        loadingMessage: "Refreshing backups...",
        successMessage: "Backup created: " + data.backup.object_name,
      });
    })
    .then(function () {
      showSubmitSuccess();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function restoreBackup(objectName) {
  if (!confirm("Restore NAT rules from this backup? Current ONA-managed rules will be replaced.")) {
    return;
  }
  setBackupStatus("Restoring backup...", false);
  requestJson("/api/backups/restore", "POST", { object_name: objectName })
    .then(function (data) {
      renderNatTables(data.dnat_rules || {}, data.snat_rules || {});
      setBackupStatus("Backup restored.", false);
      showSubmitSuccess();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function deleteBackup(objectName) {
  if (!confirm("Delete this backup object from Object Storage?")) {
    return;
  }
  setBackupStatus("Deleting backup...", false);
  requestJson("/api/backups/delete", "POST", { object_name: objectName })
    .then(function () {
      return loadBackupState({
        preservePolicy: true,
        loadingMessage: "Refreshing backups...",
        successMessage: "Backup deleted.",
      });
    })
    .then(function () {
      showSubmitSuccess();
    })
    .catch(function (error) {
      setBackupStatus(error.message, true);
      alert(error.message);
    });
}

function setText(id, value) {
  var element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setProgress(id, value) {
  var element = document.getElementById(id);
  if (!element) {
    return;
  }
  var percent = Number(value || 0);
  percent = Math.max(0, Math.min(100, percent));
  element.style.width = percent + "%";
  element.setAttribute("aria-valuenow", percent);
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toFixed(1) + "%";
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatRateBytes(value) {
  return formatBytes(value || 0) + "/s";
}

function formatRatePackets(value) {
  return Number(value || 0).toFixed(1) + " pkt/s";
}

function formatPercentTick(value) {
  return Math.round(Number(value || 0)) + "%";
}

function formatCompactNumber(value) {
  var numberValue = Number(value || 0);
  var absoluteValue = Math.abs(numberValue);
  if (absoluteValue >= 1000000000) {
    return (numberValue / 1000000000).toFixed(1).replace(/\.0$/, "") + "B";
  }
  if (absoluteValue >= 1000000) {
    return (numberValue / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  }
  if (absoluteValue >= 1000) {
    return (numberValue / 1000).toFixed(1).replace(/\.0$/, "") + "K";
  }
  if (absoluteValue >= 10 || Number.isInteger(numberValue)) {
    return Math.round(numberValue).toLocaleString();
  }
  return numberValue.toFixed(1);
}

function formatByteRateTick(value) {
  var bytes = Number(value || 0);
  if (bytes < 1024) {
    return Math.round(bytes) + " B/s";
  }
  if (bytes < 1024 * 1024) {
    return Math.round(bytes / 1024) + " KB/s";
  }
  return (bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0).replace(/\.0$/, "") + " MB/s";
}

function formatPacketRateTick(value) {
  var packets = Number(value || 0);
  if (Math.abs(packets) >= 1000) {
    return (packets / 1000).toFixed(1).replace(/\.0$/, "") + "K pkt/s";
  }
  return Math.round(packets) + " pkt/s";
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  var numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

var dashboardChartDefinitions = [
  {
    id: "cpu",
    yLabel: "CPU %",
    format: formatPercent,
    tickFormat: formatPercentTick,
    min: 0,
    max: 100,
    value: function (sample) {
      return numberOrNull(sample.cpu && sample.cpu.percent);
    },
  },
  {
    id: "memory",
    yLabel: "Memory %",
    format: formatPercent,
    tickFormat: formatPercentTick,
    min: 0,
    max: 100,
    value: function (sample) {
      return numberOrNull(sample.memory && sample.memory.percent);
    },
  },
  {
    id: "ports",
    yLabel: "Ports used",
    format: formatNumber,
    tickFormat: formatCompactNumber,
    value: function (sample) {
      return numberOrNull(sample.nat && sample.nat.ports_in_use);
    },
  },
  {
    id: "connections",
    yLabel: "Connections",
    format: formatNumber,
    tickFormat: formatCompactNumber,
    value: function (sample) {
      return numberOrNull(sample.nat && sample.nat.total_connections);
    },
  },
  {
    id: "network",
    yLabel: "Bytes/s",
    format: formatRateBytes,
    tickFormat: formatByteRateTick,
    value: function (sample) {
      var rates = sample.network && sample.network.rates;
      return numberOrNull(rates && rates.total_bytes_per_second);
    },
  },
  {
    id: "packets",
    yLabel: "Packets/s",
    format: formatRatePackets,
    tickFormat: formatPacketRateTick,
    value: function (sample) {
      var rates = sample.network && sample.network.rates;
      return numberOrNull(rates && rates.total_packets_per_second);
    },
  },
];

function sampleEpoch(sample) {
  if (sample && sample.epoch !== undefined) {
    return Number(sample.epoch);
  }
  var timestamp = sample ? Date.parse(sample.timestamp) : NaN;
  return Number.isNaN(timestamp) ? null : timestamp / 1000;
}

function addDashboardSamples(samples) {
  var byTimestamp = new Map();
  for (let sample of dashboardHistory) {
    var existingEpoch = sampleEpoch(sample);
    if (existingEpoch !== null) {
      byTimestamp.set(String(existingEpoch), sample);
    }
  }
  for (let sample of samples || []) {
    var epoch = sampleEpoch(sample);
    if (epoch === null) {
      continue;
    }
    sample.epoch = epoch;
    byTimestamp.set(String(epoch), sample);
  }

  var cutoff = Date.now() / 1000 - 86400;
  dashboardHistory = Array.from(byTimestamp.values())
    .filter(function (sample) {
      return sampleEpoch(sample) >= cutoff;
    })
    .sort(function (a, b) {
      return sampleEpoch(a) - sampleEpoch(b);
    });
}

function filteredDashboardHistory() {
  var cutoff = Date.now() / 1000 - dashboardRangeSeconds;
  return dashboardHistory.filter(function (sample) {
    return sampleEpoch(sample) >= cutoff;
  });
}

function setupDashboardCharts() {
  var rangeSelect = document.getElementById("dashboard-range");
  if (!rangeSelect) {
    return;
  }
  dashboardRangeSeconds = Number(rangeSelect.value || 3600);
  rangeSelect.addEventListener("change", function () {
    dashboardRangeSeconds = Number(rangeSelect.value || 3600);
    loadDashboardHistory();
  });
  if (!dashboardChartResizeListenerAttached) {
    window.addEventListener("resize", function () {
      clearTimeout(dashboardChartResizeTimer);
      dashboardChartResizeTimer = setTimeout(renderDashboardCharts, 150);
    });
    dashboardChartResizeListenerAttached = true;
  }
}

function loadDashboardHistory() {
  if (!document.getElementById("stats-panel")) {
    return;
  }
  requestJson("/api/dashboard/history?range=" + encodeURIComponent(dashboardRangeSeconds), "GET")
    .then(function (data) {
      addDashboardSamples(data.samples || []);
      renderDashboardCharts();
    })
    .catch(function (error) {
      console.error(error);
      renderDashboardCharts();
    });
}

function svgNode(tag, attrs) {
  var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (let key of Object.keys(attrs || {})) {
    node.setAttribute(key, attrs[key]);
  }
  return node;
}

function formatChartTime(epoch) {
  var date = new Date(epoch * 1000);
  if (dashboardRangeSeconds >= 86400) {
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric" });
  }
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function niceChartNumber(value, round) {
  if (!value || value <= 0) {
    return 1;
  }
  var exponent = Math.floor(Math.log10(value));
  var fraction = value / Math.pow(10, exponent);
  var niceFraction;
  if (round) {
    if (fraction < 1.5) {
      niceFraction = 1;
    } else if (fraction < 3) {
      niceFraction = 2;
    } else if (fraction < 7) {
      niceFraction = 5;
    } else {
      niceFraction = 10;
    }
  } else if (fraction <= 1) {
    niceFraction = 1;
  } else if (fraction <= 2) {
    niceFraction = 2;
  } else if (fraction <= 5) {
    niceFraction = 5;
  } else {
    niceFraction = 10;
  }
  return niceFraction * Math.pow(10, exponent);
}

function chartTicks(yMin, observedMax, fixedMax) {
  if (fixedMax !== undefined) {
    var fixedStep = (fixedMax - yMin) / 4;
    return [yMin, yMin + fixedStep, yMin + fixedStep * 2, yMin + fixedStep * 3, fixedMax];
  }

  var maxValue = Math.max(observedMax, yMin + 1);
  var step = niceChartNumber((maxValue - yMin) / 4, true);
  var yMax = Math.ceil(maxValue / step) * step;
  var ticks = [];
  for (let value = yMin; value <= yMax + step / 2; value += step) {
    ticks.push(value);
  }
  if (ticks.length < 2) {
    ticks.push(yMin + step);
  }
  return ticks;
}

function chartXTickEpochs(xMin, xMax) {
  return [xMin, xMin + (xMax - xMin) / 2, xMax];
}

function chartLeftMargin(labels, width) {
  var maxLength = labels.reduce(function (longest, label) {
    return Math.max(longest, String(label).length);
  }, 0);
  var margin = maxLength * 7 + 44;
  var maxMargin = width < 520 ? 106 : 136;
  return Math.max(86, Math.min(maxMargin, margin));
}

function appendChartText(svg, attrs, text) {
  var node = svgNode("text", attrs);
  node.textContent = text;
  svg.appendChild(node);
  return node;
}

function chartPoint(point, xMin, xMax, yMin, yMax, left, top, plotWidth, plotHeight) {
  var x = left + ((point.epoch - xMin) / (xMax - xMin)) * plotWidth;
  var y = top + plotHeight - ((point.value - yMin) / (yMax - yMin)) * plotHeight;
  return {
    x: Math.max(left, Math.min(left + plotWidth, x)),
    y: Math.max(top, Math.min(top + plotHeight, y)),
  };
}

function renderMetricChart(definition, samples) {
  var svg = document.getElementById("chart-" + definition.id);
  if (!svg) {
    return;
  }

  var bounds = svg.getBoundingClientRect();
  var width = Math.max(360, Math.round(bounds.width || svg.clientWidth || 640));
  var height = Math.max(250, Math.round(bounds.height || svg.clientHeight || 270));
  var now = Date.now() / 1000;
  var xMin = now - dashboardRangeSeconds;
  var xMax = now;
  var values = samples.map(function (sample) {
    return { epoch: sampleEpoch(sample), value: definition.value(sample) };
  }).filter(function (point) {
    return point.epoch !== null && point.value !== null && point.epoch >= xMin;
  });
  var yMin = definition.min !== undefined ? definition.min : 0;
  var observedMax = values.reduce(function (maxValue, point) {
    return Math.max(maxValue, point.value);
  }, yMin);
  var ticks = chartTicks(yMin, observedMax, definition.max);
  var tickFormatter = definition.tickFormat || definition.format;
  var tickLabels = ticks.map(function (tickValue) {
    return tickFormatter(tickValue);
  });
  var left = chartLeftMargin(tickLabels, width);
  var right = width < 520 ? 20 : 30;
  var top = 18;
  var bottom = 58;
  var plotWidth = Math.max(120, width - left - right);
  var plotHeight = Math.max(120, height - top - bottom);
  var yMax = ticks[ticks.length - 1];
  if (yMax <= yMin) {
    yMax = yMin + 1;
  }

  svg.replaceChildren();
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.setAttribute("preserveAspectRatio", "xMinYMin meet");

  for (let index = 0; index < ticks.length; index++) {
    var tickValue = ticks[index];
    var ratio = (tickValue - yMin) / (yMax - yMin);
    var y = top + plotHeight - ratio * plotHeight;
    svg.appendChild(svgNode("line", { x1: left, y1: y, x2: width - right, y2: y, class: "chart-grid-line" }));
    appendChartText(svg, { x: left - 12, y: y + 4, "text-anchor": "end", class: "chart-axis-text" }, tickLabels[index]);
  }

  svg.appendChild(svgNode("line", { x1: left, y1: top, x2: left, y2: height - bottom, class: "chart-axis" }));
  svg.appendChild(svgNode("line", { x1: left, y1: height - bottom, x2: width - right, y2: height - bottom, class: "chart-axis" }));

  var xTicks = chartXTickEpochs(xMin, xMax);
  for (let index = 0; index < xTicks.length; index++) {
    var epoch = xTicks[index];
    var x = left + ((epoch - xMin) / (xMax - xMin)) * plotWidth;
    if (index === 1) {
      svg.appendChild(svgNode("line", { x1: x, y1: top, x2: x, y2: height - bottom, class: "chart-grid-line" }));
    }
    var anchor = index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle";
    appendChartText(svg, { x: x, y: height - 30, "text-anchor": anchor, class: "chart-axis-text" }, formatChartTime(epoch));
  }

  appendChartText(svg, { x: left + plotWidth / 2, y: height - 8, "text-anchor": "middle", class: "chart-axis-label" }, "Time");
  var yLabelX = width < 520 ? 16 : 18;
  appendChartText(svg, {
    x: yLabelX,
    y: top + plotHeight / 2,
    "text-anchor": "middle",
    transform: "rotate(-90 " + yLabelX + " " + (top + plotHeight / 2) + ")",
    class: "chart-axis-label",
  }, definition.yLabel);

  if (values.length < 2) {
    appendChartText(svg, { x: left + plotWidth / 2, y: top + plotHeight / 2, "text-anchor": "middle", class: "chart-empty" }, "Collecting data");
    return;
  }

  var points = values.map(function (point) {
    var coordinates = chartPoint(point, xMin, xMax, yMin, yMax, left, top, plotWidth, plotHeight);
    return coordinates.x.toFixed(1) + "," + coordinates.y.toFixed(1);
  }).join(" ");
  svg.appendChild(svgNode("polyline", { points: points, class: "chart-line" }));
}

function renderDashboardCharts() {
  var samples = filteredDashboardHistory();
  for (let definition of dashboardChartDefinitions) {
    renderMetricChart(definition, samples);
  }
}

function renderDashboardStats(data) {
  var cpuPercent = data.cpu ? data.cpu.percent : null;
  var memory = data.memory || {};
  var nat = data.nat || {};
  var network = data.network || {};
  var rates = network.rates || {};
  var rules = data.rules || {};

  setText("metric-cpu-percent", formatPercent(cpuPercent));
  setText("metric-cpu-load", data.cpu && data.cpu.load_average && data.cpu.load_average.length
    ? "Load " + data.cpu.load_average.join(" / ")
    : "Load -");
  setProgress("metric-cpu-bar", cpuPercent || 0);

  setText("metric-memory-percent", formatPercent(memory.percent));
  setText("metric-memory-detail", formatBytes(memory.used_bytes) + " / " + formatBytes(memory.total_bytes));
  setProgress("metric-memory-bar", memory.percent || 0);

  setText("metric-ports-used", formatNumber(nat.ports_in_use) + " used");
  setText("metric-ports-detail", formatNumber(nat.available_ports) + " available of " +
    formatNumber(nat.total_available_ports) + " across " + formatNumber(nat.snat_source_ip_count || 1) + " IPs");
  setProgress("metric-ports-bar", nat.port_utilization_percent || 0);

  setText("metric-connections-total", formatNumber(nat.total_connections));
  setText("metric-conn-rate", Number(nat.connections_per_second || 0).toFixed(2) + " conn/s");
  setProgress("metric-connections-bar", nat.connection_utilization_percent || 0);

  setText("metric-throughput-bytes", formatRateBytes(rates.total_bytes_per_second));
  setText("metric-throughput-detail", "RX " + formatRateBytes(rates.rx_bytes_per_second) + " / TX " + formatRateBytes(rates.tx_bytes_per_second));
  setText("metric-throughput-packets", formatRatePackets(rates.total_packets_per_second));
  setText("metric-rule-counts", "DNAT " + formatNumber(rules.dnat) + " / SNAT " + formatNumber(rules.snat));
  setText("metric-updated", formatDate(data.timestamp));
  addDashboardSamples([data]);
  renderDashboardCharts();
}

function loadDashboardStats() {
  if (!document.getElementById("stats-panel")) {
    return;
  }
  requestJson("/api/dashboard/stats", "GET")
    .then(renderDashboardStats)
    .catch(function (error) {
      setText("metric-updated", error.message);
    });
}

function startDashboardPolling() {
  if (dashboardPollTimer) {
    return;
  }
  loadDashboardStats();
  dashboardPollTimer = window.setInterval(loadDashboardStats, 30000);
}

function startDashboardStream() {
  if (!document.getElementById("stats-panel")) {
    return;
  }
  if (!window.EventSource) {
    startDashboardPolling();
    return;
  }

  var source = new EventSource("/api/dashboard/stream");
  source.onmessage = function (event) {
    try {
      renderDashboardStats(JSON.parse(event.data));
    } catch (error) {
      console.error(error);
    }
  };
  source.onerror = function () {
    source.close();
    startDashboardPolling();
  };
}
