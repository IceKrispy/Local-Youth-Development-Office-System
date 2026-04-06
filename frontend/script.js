let BARANGAYS = [];

let isLoggedIn = false;
let allYouths = [];
let currentBarangayId = null;
let CURRENT_USER = null;
let ADMIN_ACTIVITY_REFRESH = null;

window.nextTab = window.nextTab || function(target) { console.warn('nextTab called before initialization', target); };
window.prevTab = window.prevTab || function(target) { console.warn('prevTab called before initialization', target); };

const $id = id => document.getElementById(id);
const val = id => ($id(id) && $id(id).value) || '';
const chk = id => !!($id(id) && $id(id).checked);
const setVal = (id, v) => { const e = $id(id); if (e) e.value = v || ''; };
const setChk = (id, v) => { const e = $id(id); if (e) e.checked = !!v; };

function hexToRgbArray(hex) {
	if (!hex) return null;
	hex = hex.trim();
	if (hex.startsWith('rgb')) {
		const nums = hex.replace(/[^0-9,]/g,'').split(',').map(n => parseInt(n,10));
		return nums.slice(0,3);
	}
	if (hex.startsWith('#')) {
		const h = hex.substring(1);
		if (h.length === 3) {
			return [parseInt(h[0]+h[0],16), parseInt(h[1]+h[1],16), parseInt(h[2]+h[2],16)];
		}
		if (h.length === 6) {
			return [parseInt(h.substring(0,2),16), parseInt(h.substring(2,4),16), parseInt(h.substring(4,6),16)];
		}
	}
	return null;
}

function cssVarRgb(varName, fallback) {
	try {
		const raw = getComputedStyle(document.documentElement).getPropertyValue(varName) || '';
		const rgb = hexToRgbArray(raw.trim()) || fallback;
		return rgb;
	} catch (e) { return fallback; }
}

function getSpecialCountEntries(data) {
	return [
		['PWD Male', data.pwd_male ?? 0],
		['PWD Female', data.pwd_female ?? 0],
		['PWD (Total)', data.pwd ?? 0],
		['4Ps Male', data.fourps_male ?? 0],
		['4Ps Female', data.fourps_female ?? 0],
		['4Ps Total', data.fourps ?? ((data.fourps_male ?? 0) + (data.fourps_female ?? 0))],
		['Working Male', data.working_male ?? 0],
		['Working Female', data.working_female ?? 0],
		['Working (Total)', data.working ?? ((data.working_male ?? 0) + (data.working_female ?? 0))],
		['Unemployed Male', data.unemployed_male ?? 0],
		['Unemployed Female', data.unemployed_female ?? 0],
		['Unemployed (Total)', data.unemployed ?? ((data.unemployed_male ?? 0) + (data.unemployed_female ?? 0))],
		['IP Male', data.ip_male ?? 0],
		['IP Female', data.ip_female ?? 0],
		['IP (Total)', data.ip ?? ((data.ip_male ?? 0) + (data.ip_female ?? 0))],
		['OSY Male', data.osy_male ?? 0],
		['OSY Female', data.osy_female ?? 0],
		['OSY (Total)', (data.osy != null) ? data.osy : ((data.osy_male ?? 0) + (data.osy_female ?? 0))],
	];
}

function buildSummaryRows(data) {
	const AGE_START = 15, AGE_END = 30;
	const ageCols = [];
	for (let a = AGE_START; a <= AGE_END; a++) ageCols.push(String(a));
	const rows = [];
	rows.push(['DEMOGRAPHICS', ...ageCols, 'TOTAL']);
	rows.push(['Barangay', ...ageCols.map(()=>''), data.barangay_name || '']);
	rows.push(['Total Youth', ...ageCols.map(()=>''), data.total ?? 0]);
	rows.push([]);

	rows.push(['SEX ASSIGNED BY BIRTH', ...ageCols.map(()=>''), '']);
	const sexByAge = data.sex_by_age || {};
	const sexKeys = Object.keys(sexByAge).length ? Object.keys(sexByAge) : ['Male','Female'];
	for (const s of sexKeys) {
		const rowAges = ageCols.map(a => (sexByAge[s] && sexByAge[s][a]) ? sexByAge[s][a] : 0);
		const total = rowAges.reduce((s,v)=>s+Number(v),0) || (data.sex && (data.sex[s] || data.sex[s.toLowerCase()]) ) || 0;
		rows.push([s.toUpperCase(), ...rowAges, total]);
	}
	rows.push([]);

	const ageCounts = ageCols.map(a => (data.ages && data.ages[a]) ? data.ages[a] : 0);
	rows.push(['AGE', ...ageCounts, ageCounts.reduce((s,v)=>s+Number(v),0)]);
	rows.push([]);

	rows.push(['CIVIL STATUS', ...ageCols.map(()=>''), '']);
	const civilByAge = data.civil_by_age || {};
	const csKeys = Object.keys(civilByAge).length ? Object.keys(civilByAge) : Object.keys(data.civil_status || {});
	if (csKeys.length === 0) rows.push(['No civil status data', ...ageCols.map(()=>''), '']);
	for (const k of csKeys) {
		const rowAges = ageCols.map(a => (civilByAge[k] && civilByAge[k][a]) ? civilByAge[k][a] : 0);
		const total = rowAges.reduce((s,v)=>s+Number(v),0) || (data.civil_status && (data.civil_status[k] ?? 0));
		rows.push([k.toUpperCase(), ...rowAges, total]);
	}
	rows.push([]);

	rows.push(['EDUCATION', ...ageCols.map(()=>''), '']);
	const eduByAge = data.education_by_age || {};
	const eduKeys = Object.keys(eduByAge).length ? Object.keys(eduByAge) : Object.keys(data.education || {});
	if (eduKeys.length === 0) rows.push(['No education data', ...ageCols.map(()=>''), '']);
	for (const k of eduKeys) {
		const rowAges = ageCols.map(a => (eduByAge[k] && eduByAge[k][a]) ? eduByAge[k][a] : 0);
		const total = rowAges.reduce((s,v)=>s+Number(v),0) || (data.education && (data.education[k] ?? 0));
		rows.push([k.toUpperCase(), ...rowAges, total]);
	}
	rows.push([]);

	rows.push(['SPECIAL COUNTS', ...ageCols.map(()=>''), '']);
	for (const [label, value] of getSpecialCountEntries(data)) {
		rows.push([label, ...ageCols.map(()=>''), value]);
	}

	return { ageCols, rows };
}

document.addEventListener("DOMContentLoaded", async () => {
	const path = window.location.pathname || '';
	const onLoginPage = path.endsWith('/login/') || path.endsWith('login.html') || path === '/login' || path === '/login/';
	const onRegisterPage = path.endsWith('/register/') || path.endsWith('register.html') || path === '/register' || path === '/register/';
	const onAuthPage = onLoginPage || onRegisterPage;
	const hasAdminActivitySection = !!document.getElementById('admin-account-section');

	if (onAuthPage) {
		return;
	}

	const logged = await checkUserStatus();
	if (!logged) {
		window.location.href = '/login/';
		return;
	}

	if (CURRENT_USER && CURRENT_USER.is_admin && hasAdminActivitySection) {
		fetchAdminAccountActivity();
		if (ADMIN_ACTIVITY_REFRESH) clearInterval(ADMIN_ACTIVITY_REFRESH);
		ADMIN_ACTIVITY_REFRESH = setInterval(fetchAdminAccountActivity, 30000);
	} else if (ADMIN_ACTIVITY_REFRESH) {
		clearInterval(ADMIN_ACTIVITY_REFRESH);
		ADMIN_ACTIVITY_REFRESH = null;
	}

	if (document.getElementById('barangay-grid') || document.getElementById('youth-data')) {
		fetchBarangays();
		fetchYouths();
	}
	updateTabState();
	attachAutoToggles(); 
	document.querySelectorAll('.btn-next').forEach(btn => {
		btn.addEventListener('click', (ev) => {
			const tgt = btn.getAttribute('data-target');
			if (tgt) nextTab(tgt);
		});
	});
	document.querySelectorAll('.btn-prev').forEach(btn => {
		btn.addEventListener('click', (ev) => {
			const tgt = btn.getAttribute('data-target');
			if (tgt) prevTab(tgt);
		});
	});
});

function attachAutoToggles() {
	const ids = ['disability_type','specific_needs_condition','scholarship_program','kk_assembly_times','kk_assembly_no_reason','number_of_children', 'tribe_name', 'muslim_group'];
	ids.forEach(id => {
		const el = document.getElementById(id);
		if (!el) return;
		el.addEventListener('input', updateAutoTogglesState);
		el.addEventListener('change', updateAutoTogglesState);
	});

	const modal = document.getElementById('youthModal');
	if (modal) modal.addEventListener('shown.bs.modal', () => setTimeout(updateAutoTogglesState, 10));
}

function updateAutoTogglesState() {
	const get = id => document.getElementById(id);
	const disability = get('disability_type');
	const specific = get('specific_needs_condition');
	const scholarProg = get('scholarship_program');
	const kkTimes = get('kk_assembly_times');
	const kkReason = get('kk_assembly_no_reason');
	const numChildren = get('number_of_children');

	if (disability) {
	}

	if (specific) {
		const specChk = get('has_specific_needs');
		if (specChk) specChk.checked = String(specific.value || '').trim() !== '';
	}

	if (scholarProg) {
		const schChk = get('is_scholar');
		if (schChk) schChk.checked = String(scholarProg.value || '').trim() !== '';
	}

	if (kkTimes || kkReason) {
		const kkChk = get('attended_kk_assembly');
		if (kkChk) {
			const times = parseInt(kkTimes?.value || 0) || 0;
			if (times > 0) kkChk.checked = true;
			else if (kkReason && String(kkReason.value || '').trim() !== '') kkChk.checked = false;
			else kkChk.checked = false;
		}
	}

	if (numChildren) {
		const fourChk = get('is_4ps');
		const n = parseInt(numChildren.value || 0) || 0;
		if (fourChk) fourChk.checked = n > 0;
	}

	const tribe = get('tribe_name');
	if (tribe) {
		const ipChk = get('is_ip');
		if (ipChk) ipChk.checked = String(tribe.value || '').trim() !== '';
	}

	const mg = get('muslim_group');
	if (mg) {
		const muslimChk = get('is_muslim');
		if (muslimChk) muslimChk.checked = String(mg.value || '').trim() !== '';
	}
}

function fetchBarangays() {
	fetch('/api/barangays/').then(res => res.json()).then(data => {
		if (Array.isArray(data) && data.length) {
			BARANGAYS = data;
		}
		renderDashboard();
		populateBarangayDropdown();
	}).catch(err => {
		console.warn('Could not fetch barangays, falling back to empty list', err);
		renderDashboard();
		populateBarangayDropdown();
	});
}

function getYouthById(id) {
	return allYouths.find(y => y.id == id);
}

function renderDashboard() {
	const grid = document.getElementById('barangay-grid');
	const pageSub = document.getElementById('dashboard-page-sub');
	const counts = {};
	if (Array.isArray(allYouths)) {
		allYouths.forEach(y => {
			const id = String(y.barangay_id);
			counts[id] = (counts[id] || 0) + 1;
		});
	}

	if (pageSub) {
		if (CURRENT_USER && !CURRENT_USER.is_admin && CURRENT_USER.barangay_name) {
			pageSub.textContent = `Youth records for ${CURRENT_USER.barangay_name}, Manolo Fortich, Bukidnon`;
		} else {
			pageSub.textContent = 'Youth records across 22 barangays of Manolo Fortich, Bukidnon';
		}
	}

	const PALETTE = ['#2351a6','#059669','#7c3aed','#d97706','#0284c7','#e11d48','#15803d','#9333ea','#c2410c','#0891b2','#1d4ed8','#b45309'];

	grid.innerHTML = BARANGAYS.map((b, idx) => {
		const cnt        = counts[String(b.id)] || 0;
		const color      = PALETTE[idx % PALETTE.length];
		const countLabel = cnt === 1 ? '1 youth' : cnt + ' youth';
		const num        = String(idx + 1).padStart(2, '0');
		return `
		<div class="barangay-card" onclick="openBarangay(${b.id}, '${b.name}')">
			<div class="bc-banner" style="background:${color};">
				<div class="bc-orb bc-orb-a"></div>
				<div class="bc-orb bc-orb-b"></div>
				<div class="bc-orb bc-orb-c"></div>
				<span class="bc-num">${num}</span>
			</div>
			<div class="bc-body">
				<div class="bc-name">${b.name}</div>
				<div class="bc-loc">
					<svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
					Manolo Fortich, Bukidnon
				</div>
				<div class="bc-footer">
					<span class="bc-count" style="color:${color};background:${color}14;border:1px solid ${color}28;">
						<svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
						${countLabel}
					</span>
					<span class="bc-arrow" style="color:${color};">
						<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
					</span>
				</div>
			</div>
		</div>
		`}).join('');
}

function filterBarangayGrid(term) {
    term = (term || '').toLowerCase();
    const grid = document.getElementById('barangay-grid');
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll('.barangay-card'));
    cards.forEach((card, idx) => {
        const name = (BARANGAYS[idx] && BARANGAYS[idx].name || '').toLowerCase();
        card.style.display = name.includes(term) ? '' : 'none';
    });
}

async function fetchBarangaySummary(bid) {
	const res = await fetch(`/api/barangay_summary/${bid}/`);
	if (!res.ok) throw new Error('Failed to fetch summary: ' + res.status);
	return res.json();
}

function viewBarangaySummary() {
	if (!currentBarangayId) return alert('Open a barangay first');
	fetchBarangaySummary(currentBarangayId).then(data => {
		const content = document.getElementById('summary-content');
		const specialCountItems = getSpecialCountEntries(data)
			.map(([label, value]) => `<li>${label}: <strong>${value}</strong></li>`)
			.join('');
		const buildRows = (obj, sortNumeric=false) => {
			if (!obj || typeof obj !== 'object' || Object.keys(obj).length === 0) return '<tr><td class="text-muted">No data</td><td></td></tr>';
			const keys = Object.keys(obj);
			if (sortNumeric) keys.sort((a,b)=>Number(a)-Number(b)); else keys.sort();
			return keys.map(k => `<tr><td>${k}</td><td class="text-end">${obj[k]}</td></tr>`).join('');
		};

		content.innerHTML = `
			<h5>${data.barangay_name} Summary</h5>
			<p><strong>Total youth:</strong> ${data.total}</p>
			<div class="row">
				<div class="col-md-6">
					<h6 class="mt-3">Sex</h6>
					<table class="table table-sm table-borderless">
						<tbody>${buildRows(data.sex)}</tbody>
					</table>
					<h6 class="mt-3">Civil Status</h6>
					<table class="table table-sm table-borderless">
						<tbody>${buildRows(data.civil_status)}</tbody>
					</table>
				</div>
				<div class="col-md-6">
					<h6 class="mt-3">Ages</h6>
					<table class="table table-sm table-borderless">
						<tbody>${buildRows(data.ages, true)}</tbody>
					</table>
					<h6 class="mt-3">Education</h6>
					<table class="table table-sm table-borderless">
						<tbody>${buildRows(data.education)}</tbody>
					</table>
				</div>
			</div>
			<div class="mt-3">
				<p><strong>Special counts:</strong></p>
				<ul>${specialCountItems}</ul>
			</div>
		`;
		new bootstrap.Modal(document.getElementById('summaryModal')).show();
	}).catch(err => alert(err.message));
}

function downloadBarangaySummaryCSV() {
	if (!currentBarangayId) return alert('Open a barangay first');
	fetchBarangaySummary(currentBarangayId).then(data => {
		const { rows } = buildSummaryRows(data);
		const csv = rows.map(r => r.map(cell => '"' + (cell ?? '') + '"').join(',')).join('\n');
		const blob = new Blob([csv], {type: 'text/csv'});
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a'); a.href = url;
		a.download = `${(data.barangay_name||'Barangay').replace(/\s+/g,'_')}_demographics_summary.csv`;
		document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
	}).catch(err => alert(err.message));
}

function downloadBarangaySummaryPDF() {
	if (!currentBarangayId) return alert('Open a barangay first');
	fetchBarangaySummary(currentBarangayId).then(data => {
		try {
			const jsPDF = (window.jspdf && window.jspdf.jsPDF) ? window.jspdf.jsPDF : (window.jsPDF || null);
			if (!jsPDF) return alert('PDF library not loaded');

			const { ageCols, rows: body } = buildSummaryRows(data);
			const head = ['DEMOGRAPHICS', ...ageCols, 'TOTAL'];

			const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });
			if (typeof doc.autoTable !== 'function') return alert('jsPDF AutoTable plugin not loaded');
			const pageWidth = doc.internal.pageSize.getWidth();
			let startY = 40;

			doc.setFontSize(10);
			doc.text('Republic of the Philippines', pageWidth/2, startY, { align: 'center' }); startY += 14;
			doc.text('Province of Bukidnon', pageWidth/2, startY, { align: 'center' }); startY += 14;
			doc.text('Municipality of Manolo Fortich', pageWidth/2, startY, { align: 'center' }); startY += 28;
			doc.setFontSize(16);
			doc.text((data.barangay_name || 'BARANGAY').toUpperCase(), pageWidth/2, startY, { align: 'center' }); startY += 20;
			doc.setFontSize(12);
			doc.text('OFFICE OF THE SANGGUNIANG KABATAAN', pageWidth/2, startY, { align: 'center' }); startY += 16;
			doc.setFontSize(13);
			doc.text('SUMMARY OF KATIPUNAN NG KABATAAN (KK) PROFILING', pageWidth/2, startY, { align: 'center' }); startY += 18;

			doc.setFontSize(9);
			const para = 'Section 5(b) of the Implementing Rules and Regulations (IRR) of RA No. 10742 states that the Katipunan ng Kabataan (KK) shall serve as the highest policymaking body to decide on matters affecting the youth in the barangay.';
			const split = doc.splitTextToSize(para, pageWidth - 80);
			doc.text(split, 40, startY); startY += split.length * 10 + 6;

			const headerColor = cssVarRgb('--pdf-header', [0,123,67]);
			const rowColor = cssVarRgb('--pdf-row', [240,250,240]);
			const firstColColor = cssVarRgb('--pdf-firstcol', [0,86,63]);
			const borderColor = cssVarRgb('--pdf-border', [150,150,150]);

			doc.autoTable({
				startY: startY,
				head: [head],
				body: body,
				theme: 'grid',
				tableWidth: 'auto',
				headStyles: {
					fillColor: headerColor,
					textColor: 255,
					halign: 'center',
					fontStyle: 'bold'
				},
				styles: {
					fontSize: 9,
					cellPadding: 4,
					textColor: 50,
					valign: 'middle'
				},
				alternateRowStyles: { fillColor: rowColor },
				tableLineColor: borderColor,
				tableLineWidth: 0.4,
				columnStyles: {
					0: { cellWidth: 140, halign: 'left' },
					[head.length-1]: { cellWidth: 60, halign: 'center' }
				},
				didParseCell: function (dataArg) {
					if (dataArg.cell.section === 'body' && dataArg.column.index === 0) {
						dataArg.cell.styles.fontStyle = 'bold';
						dataArg.cell.styles.textColor = firstColColor;
					}
					if (dataArg.cell.section === 'head') {
						dataArg.cell.styles.cellPadding = 6;
					}
				}
			});

			const filename = `${(data.barangay_name || 'Barangay').replace(/\s+/g,'_')}_demographics_summary.pdf`;
			doc.save(filename);
		} catch (err) {
			console.error('PDF generation error:', err);
			alert('Failed to generate PDF: ' + (err.message || err));
		}
	}).catch(err => alert(err.message));
}

function downloadBlankYouthForm() {
	if (!currentBarangayId) return alert('Open a barangay first');
	window.location.href = `/api/forms/youth-profile/${currentBarangayId}/`;
}

function downloadAllBlankYouthForms() {
	window.location.href = '/api/forms/youth-profile-pack/';
}

function populateBarangayDropdown() {
	const select = $id('barangay_id');
	if (!select) return;
	select.innerHTML = BARANGAYS.map(b => `<option value="${b.id}">${b.name}</option>`).join('');
}

function openBarangay(id, name) {
	currentBarangayId = id;
	document.getElementById('current-barangay-title').innerText = `${name} Youth Records`;
	document.getElementById('dashboard-view').style.display = 'none';
	document.getElementById('list-view').style.display = 'block';
	const searchInput = document.getElementById('searchInput');
	const searchFilter = document.getElementById('searchFilter');
	if (searchInput) searchInput.value = '';
	if (searchFilter) searchFilter.value = 'all';
	updateYouthSearchPlaceholder();
	filterTable();

	fetchBarangaySummary(currentBarangayId).then(data => {
		const youths = Array.isArray(allYouths) ? allYouths.filter(y => String(y.barangay_id) === String(currentBarangayId)) : [];
		const total = (data && data.total != null) ? data.total : youths.length;
		const inSchool = youths.filter(y => toBool(y.is_in_school) || (y.full_data && toBool(y.full_data.is_in_school))).length;
		const osy = (data && data.osy != null) ? data.osy : youths.filter(y => toBool(y.is_osy) || (y.full_data && toBool(y.full_data.is_osy))).length;
		const registered = youths.filter(y => {
			const sk  = toBool(y.registered_voter_sk)  || (y.full_data && toBool(y.full_data.registered_voter_sk));
			const nat = toBool(y.registered_voter_national) || (y.full_data && toBool(y.full_data.registered_voter_national));
			return sk || nat;
		}).length;

		setStat('stat-total', total);
		setStat('stat-in-school', inSchool);
		setStat('stat-osy', osy);
		setStat('stat-registered', registered);
	}).catch(err => {
		console.warn('Failed fetching barangay summary for top stats:', err);
		renderTopStats();
	});
}

function showDashboard() {
	currentBarangayId = null;
	document.getElementById('dashboard-view').style.display = 'block';
	document.getElementById('list-view').style.display = 'none';
}

function showAdminAccountSection() {
	window.location.href = '/account/';
}

function checkUserStatus() {
	return fetch('/api/user/').then(res => res.ok ? res.json() : null).then(data => {
		const userDisplay = document.getElementById('user-display');
		const usernameSpan = document.getElementById('username-span');
		const accountLabel = document.getElementById('account-label');
		const loginBtn = document.getElementById('login-btn');
		const logoutBtn = document.getElementById('logout-btn');
		const adminAccountSection = document.getElementById('admin-account-section');

		if (data && data.is_authenticated) {
			isLoggedIn = true;
			CURRENT_USER = data;
			if (userDisplay) userDisplay.style.display = 'block';
			if (usernameSpan) {
				usernameSpan.innerText = data.barangay_name && !data.is_admin
					? `${data.username} (${data.barangay_name})`
					: data.username;
			}
			if (accountLabel) accountLabel.innerText = data.is_admin ? 'Admin' : 'Account';
			if (loginBtn) loginBtn.style.display = 'none';
			if (logoutBtn) logoutBtn.style.display = 'block';
			document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'inline-block');
			document.querySelectorAll('.system-admin-only').forEach(el => el.style.display = data.is_admin ? '' : 'none');
			if (adminAccountSection) adminAccountSection.style.display = data.is_admin ? 'block' : 'none';
			return true;
		} else {
			isLoggedIn = false;
			CURRENT_USER = null;
			if (userDisplay) userDisplay.style.display = 'none';
			if (usernameSpan) usernameSpan.innerText = '';
			if (accountLabel) accountLabel.innerText = 'Account';
			if (loginBtn) loginBtn.style.display = 'inline-block';
			if (logoutBtn) logoutBtn.style.display = 'none';
			document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
			document.querySelectorAll('.system-admin-only').forEach(el => el.style.display = 'none');
			if (adminAccountSection) adminAccountSection.style.display = 'none';
			return false;
		}
	}).catch(err => {
		console.debug('checkUserStatus error:', err);
		isLoggedIn = false;
		CURRENT_USER = null;
		return false;
	});
}

function showLoginModal() { new bootstrap.Modal(document.getElementById('authModal')).show(); }

function handleAuth(e) {
	e.preventDefault();
	const loadingEl = document.getElementById('login-loading');
	const textEl    = document.getElementById('login-text');
	const submitBtn = document.getElementById('login-submit');
	const errorDiv  = document.getElementById('login-error');
	const errorMsg  = document.getElementById('login-error-msg');

	if (loadingEl) loadingEl.style.display = 'flex';
	if (textEl)    textEl.style.display    = 'none';
	if (submitBtn) submitBtn.disabled = true;
	if (errorDiv)  errorDiv.classList.remove('show');

	fetch('/api/login/', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify({
			username: document.getElementById('auth-username').value,
			password: document.getElementById('auth-password').value
		})
	}).then(res => res.json()).then(data => {
		if (data.message) {
			window.location.href = '/';
		} else {
			if (errorDiv && errorMsg) {
				errorMsg.textContent = data.error || 'Invalid credentials. Please try again.';
				errorDiv.classList.add('show');
			} else { alert(data.error); }
			if (loadingEl) loadingEl.style.display = 'none';
			if (textEl)    textEl.style.display    = 'flex';
			if (submitBtn) submitBtn.disabled = false;
		}
	}).catch(err => {
		if (errorDiv && errorMsg) {
			errorMsg.textContent = 'Connection error. Please try again.';
			errorDiv.classList.add('show');
		} else { alert('Login failed: ' + (err.message || err)); }
		if (loadingEl) loadingEl.style.display = 'none';
		if (textEl)    textEl.style.display    = 'flex';
		if (submitBtn) submitBtn.disabled = false;
	});
}

function handleRegister(e) {
	e.preventDefault();
	const loadingEl = document.getElementById('register-loading');
	const textEl = document.getElementById('register-text');
	const submitBtn = document.getElementById('register-submit');
	const errorDiv = document.getElementById('register-error');
	const errorMsg = document.getElementById('register-error-msg');

	const username = (document.getElementById('register-username')?.value || '').trim();
	const email = (document.getElementById('register-email')?.value || '').trim();
	const barangayId = document.getElementById('register-barangay')?.value || '';
	const password = document.getElementById('register-password')?.value || '';
	const confirmPassword = document.getElementById('register-confirm-password')?.value || '';

	if (errorDiv) errorDiv.classList.remove('show');

	if (!username || !password || !barangayId) {
		if (errorDiv && errorMsg) {
			errorMsg.textContent = 'Username, password, and assigned barangay are required.';
			errorDiv.classList.add('show');
		}
		return;
	}

	if (password !== confirmPassword) {
		if (errorDiv && errorMsg) {
			errorMsg.textContent = 'Passwords do not match.';
			errorDiv.classList.add('show');
		}
		return;
	}

	if (loadingEl) loadingEl.style.display = 'flex';
	if (textEl) textEl.style.display = 'none';
	if (submitBtn) submitBtn.disabled = true;

	fetch('/api/register/', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify({
			username: username,
			email: email,
			password: password,
			barangay_id: barangayId
		})
	}).then(res => res.json()).then(data => {
		if (data.message) {
			window.location.href = '/';
			return;
		}

		if (errorDiv && errorMsg) {
			errorMsg.textContent = data.error || 'Registration failed. Please try again.';
			errorDiv.classList.add('show');
		} else {
			alert(data.error || 'Registration failed.');
		}

		if (loadingEl) loadingEl.style.display = 'none';
		if (textEl) textEl.style.display = 'flex';
		if (submitBtn) submitBtn.disabled = false;
	}).catch(err => {
		if (errorDiv && errorMsg) {
			errorMsg.textContent = 'Connection error. Please try again.';
			errorDiv.classList.add('show');
		} else {
			alert('Registration failed: ' + (err.message || err));
		}

		if (loadingEl) loadingEl.style.display = 'none';
		if (textEl) textEl.style.display = 'flex';
		if (submitBtn) submitBtn.disabled = false;
	});
}

function logout() { fetch('/api/logout/').then(() => window.location.reload()); }

function fetchYouths() {
	fetch('/api/youth/').then(res => res.json()).then(data => {
		allYouths = data;
		renderTopStats();
		renderDashboard();
		if(currentBarangayId) filterTable();
	});
}

function formatNumber(n) { return (typeof n === 'number') ? n.toLocaleString() : n; }

function formatDateTime(value) {
	if (!value) return 'Not yet';
	const dt = new Date(value);
	if (Number.isNaN(dt.getTime())) return value;
	return dt.toLocaleString();
}

function toBool(v) {
	if (v === true || v === 1 || v === '1' || v === 'true' || v === 'True') return true;
	return false;
}

function renderTopStats() {
	const total = Array.isArray(allYouths) ? allYouths.length : 0;
	const inSchool = Array.isArray(allYouths)
		? allYouths.filter(y => toBool(y.is_in_school) || (y.full_data && toBool(y.full_data.is_in_school))).length : 0;
	const osy = Array.isArray(allYouths)
		? allYouths.filter(y => toBool(y.is_osy) || (y.full_data && toBool(y.full_data.is_osy))).length : 0;
	const registered = Array.isArray(allYouths)
		? allYouths.filter(y => {
			const sk  = toBool(y.registered_voter_sk)  || (y.full_data && toBool(y.full_data.registered_voter_sk));
			const nat = toBool(y.registered_voter_national) || (y.full_data && toBool(y.full_data.registered_voter_national));
			return sk || nat;
		}).length : 0;

	const set = (id, value) => { const el = document.getElementById(id); if (el) el.innerText = formatNumber(value); };
	set('stat-total', total);
	set('stat-in-school', inSchool);
	set('stat-osy', osy);
	set('stat-registered', registered);

	if (total === 0 && Array.isArray(BARANGAYS) && BARANGAYS.length > 0) {
		fetchAggregatedStats();
	}
}

async function fetchAggregatedStats() {
	try {
		let grandTotal = 0, grandOsy = 0;
		const results = await Promise.all(
			BARANGAYS.map(b => fetch(`/api/barangay_summary/${b.id}/`).then(r => r.ok ? r.json() : null).catch(() => null))
		);
		results.forEach(data => {
			if (!data) return;
			grandTotal += Number(data.total || 0);
			grandOsy   += Number(data.osy   || 0);
		});
		if (grandTotal > 0) {
			setStat('stat-total', grandTotal);
			setStat('stat-osy', grandOsy);
		}
	} catch(e) { console.warn('fetchAggregatedStats failed:', e); }
}

function setStat(id, value) { const el = document.getElementById(id); if (el) el.innerText = formatNumber(value); }

function renderAdminAccountActivity(payload) {
	const section = document.getElementById('admin-account-section');
	const tbody = document.getElementById('admin-account-rows');
	const empty = document.getElementById('admin-account-empty');
	const summary = document.getElementById('admin-account-summary');
	if (!section || !tbody || !empty || !summary) return;

	if (!CURRENT_USER || !CURRENT_USER.is_admin) {
		section.style.display = 'none';
		return;
	}

	section.style.display = 'block';
	const rows = Array.isArray(payload?.rows) ? payload.rows : [];
	const activeBarangays = Array.isArray(payload?.active_barangays) ? payload.active_barangays : [];
	summary.textContent = rows.length
		? `${payload.active_count || 0} active account(s) right now. Active barangays: ${activeBarangays.length ? activeBarangays.join(', ') : 'none'}.`
		: 'No assigned barangay accounts available.';

	if (!rows.length) {
		tbody.innerHTML = '';
		empty.style.display = 'block';
		return;
	}

	empty.style.display = 'none';
	tbody.innerHTML = rows.map(row => {
		const statusClass = row.is_logged_in ? 'green' : (row.is_account_active ? 'navy' : 'rose');
		const statusLabel = row.is_logged_in ? 'Active Now' : (row.is_account_active ? 'Offline' : 'Disabled');
		const safeUsername = String(row.username).replace(/'/g, "\\'");
		const actionButton = row.is_account_active
			? `<button class="btn-tbl delete" onclick="disableBarangayAccount(${row.user_id}, '${safeUsername}')">Disable</button>`
			: `<button class="btn-tbl view" onclick="enableBarangayAccount(${row.user_id}, '${safeUsername}')">Enable</button>`;
		return `
			<tr>
				<td>${row.username}</td>
				<td>${row.barangay_name || 'Unassigned'}</td>
				<td><span class="badge-pill ${statusClass}">${statusLabel}</span></td>
				<td>${formatDateTime(row.login_time)}</td>
				<td>${formatDateTime(row.logout_time)}</td>
				<td>${actionButton}</td>
			</tr>
		`;
	}).join('');
}

function fetchAdminAccountActivity() {
	if (!CURRENT_USER || !CURRENT_USER.is_admin) return;
	if (!document.getElementById('admin-account-section')) return;
	fetch('/api/admin/account-activity/')
		.then(res => res.ok ? res.json() : Promise.reject(new Error('Failed to load account activity')))
		.then(renderAdminAccountActivity)
		.catch(err => {
			console.warn('Failed to load admin account activity:', err);
			const summary = document.getElementById('admin-account-summary');
			if (summary) summary.textContent = 'Unable to load account activity right now.';
		});
}

function disableBarangayAccount(userId, username) {
	if (!CURRENT_USER || !CURRENT_USER.is_admin) return;
	if (!confirm(`Disable the account for ${username}?`)) return;
	fetch('/api/admin/disable-account/', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify({ user_id: userId })
	}).then(res => res.json()).then(data => {
		if (data.message) {
			fetchAdminAccountActivity();
			return;
		}
		alert(data.error || 'Failed to disable account.');
	}).catch(err => {
		alert('Failed to disable account: ' + (err.message || err));
	});
}

function enableBarangayAccount(userId, username) {
	if (!CURRENT_USER || !CURRENT_USER.is_admin) return;
	if (!confirm(`Enable the account for ${username}?`)) return;
	fetch('/api/admin/enable-account/', {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify({ user_id: userId })
	}).then(res => res.json()).then(data => {
		if (data.message) {
			fetchAdminAccountActivity();
			return;
		}
		alert(data.error || 'Failed to enable account.');
	}).catch(err => {
		alert('Failed to enable account: ' + (err.message || err));
	});
}

function updateYouthSearchPlaceholder() {
	const input = document.getElementById('searchInput');
	const filter = document.getElementById('searchFilter');
	if (!input || !filter) return;
	const placeholders = {
		all: 'Search all youth information...',
		name: 'Search by youth name...',
		age: 'Search by age...',
		sex: 'Search by sex...',
		purok: 'Search by purok...',
		education: 'Search by education...'
	};
	input.placeholder = placeholders[filter.value] || placeholders.all;
}

function filterTable() {
	if (!currentBarangayId) return;
	const input = document.getElementById('searchInput');
	const filter = document.getElementById('searchFilter');
	const term = ((input && input.value) || '').trim().toLowerCase();
	const filterType = (filter && filter.value) || 'all';
	const filtered = allYouths.filter(y => 
		String(y.barangay_id) === String(currentBarangayId) && 
		matchesYouthSearch(y, term, filterType)
	);
	renderRows(filtered);
}

function matchesYouthSearch(y, term, filterType) {
	if (!term) return true;
	const details = y.full_data || {};
	const values = {
		name: String(y.name || '').toLowerCase(),
		age: String(y.age ?? '').toLowerCase(),
		sex: String(y.sex || '').toLowerCase(),
		purok: String(details.purok || '').toLowerCase(),
		education: String(y.education_level || '').toLowerCase(),
	};
	if (filterType === 'all') return Object.values(values).some(value => value.includes(term));
	return (values[filterType] || '').includes(term);
}

function renderRows(data) {
	const tbody = document.getElementById('youth-data');
	const emptyMsg = document.getElementById('empty-msg');
	if (data.length === 0) {
		tbody.innerHTML = '';
		emptyMsg.style.display = 'block';
		return;
	}
	emptyMsg.style.display = 'none';
    
	tbody.innerHTML = data.map(y => `
		<tr>
			<td>${y.name}</td>
			<td>${y.age}</td>
			<td>${y.sex}</td>
			<td>${y.full_data.purok || '-'}</td>
			<td>${y.education_level}</td>
			<td class="admin-only">
			<div style="display:flex;gap:6px;">
				<button class="btn-tbl view" onclick="viewFullSummary(${y.id})">
					<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
					View
				</button>
				<button class="btn-tbl edit" onclick="editYouth(${y.id})">
					<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
					Edit
				</button>
				<button class="btn-tbl delete" onclick="deleteYouth(${y.id})">
					<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
					Delete
				</button>
			</div>
			</td>
		</tr>
	`).join('');
    
	if(isLoggedIn) document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'table-cell');
}

function openModal() {
	document.getElementById('youthForm').reset();
	document.getElementById('youth-id').value = '';
	if (currentBarangayId) document.getElementById('barangay_id').value = currentBarangayId;
	toggleOSY();
	updateAutoTogglesState();
	document.querySelectorAll('.edit-save-btn').forEach(btn => btn.style.display = 'none');
	if (typeof switchTab === 'function') {
		switchTab('tab-personal',
			document.querySelector('.modal-tab-btn[onclick*="tab-personal"]'));
	}
	new bootstrap.Modal(document.getElementById('youthModal')).show();
}

function editYouth(id) {
	const y = getYouthById(id);
	if (!y) return alert("Error: Data not found");
	const d = y.full_data || {};

	const mappings = {
		'youth-id': y.id,
		'name': y.name,
		'birthdate': d.birthdate,
		'sex': y.sex || d.sex,
		'civil_status': d.civil_status,
		'religion': d.religion,
		'barangay_id': d.barangay_id,
		'purok': d.purok,
		'email': d.email,
		'contact_number': d.contact_number,
		'osy_program_type': d.osy_program_type,
		'osy_reason_no_enroll': d.osy_reason_no_enroll,
		'disability_type': d.disability_type,
		'specific_needs_condition': d.specific_needs_condition,
		'tribe_name': d.tribe_name,
		'muslim_group': d.muslim_group,
		'education_level': y.education_level,
		'course': d.course,
		'school_name': d.school_name,
		'scholarship_program': d.scholarship_program,
		'work_status': d.work_status,
		'kk_assembly_times': d.kk_assembly_times,
		'kk_assembly_no_reason': d.kk_assembly_no_reason,
		'number_of_children': d.number_of_children
	};

	Object.entries(mappings).forEach(([k,v]) => setVal(k, v));

	const checks = ['is_in_school','is_osy','osy_willing_to_enroll','is_working_youth','is_unemployed_youth','is_pwd','has_specific_needs','is_ip','is_muslim','is_scholar','registered_voter_sk','registered_voter_national','voted_last_sk','attended_kk_assembly','is_4ps'];
	checks.forEach(id => setChk(id, d[id] || y[id] || false));

	toggleOSY();
	updateAutoTogglesState();
	document.querySelectorAll('.edit-save-btn').forEach(btn => btn.style.display = '');
	if (typeof switchTab === 'function') {
		switchTab('tab-personal',
			document.querySelector('.modal-tab-btn[onclick*="tab-personal"]'));
	}
	new bootstrap.Modal($id('youthModal')).show();
}

function saveYouth(e) {
	e.preventDefault();
	const getVal = (id) => document.getElementById(id).value;
	const getCheck = (id) => document.getElementById(id).checked;

	let kk_times = parseInt(getVal('kk_assembly_times')) || 0;
	let num_children = parseInt(getVal('number_of_children')) || 0;

	const data = {
		name: getVal('name'),
		birthdate: getVal('birthdate'),
		sex: getVal('sex'),
		civil_status: getVal('civil_status'),
		religion: getVal('religion'),
		barangay_id: parseInt(getVal('barangay_id')) || currentBarangayId,
		purok: getVal('purok'),
		email: getVal('email'),
		contact_number: getVal('contact_number'),
		is_in_school: getCheck('is_in_school'),
		is_osy: getCheck('is_osy'),
		osy_willing_to_enroll: getCheck('osy_willing_to_enroll'),
		osy_program_type: getVal('osy_program_type'),
		osy_reason_no_enroll: getVal('osy_reason_no_enroll'),
		is_working_youth: getCheck('is_working_youth'),
		is_unemployed_youth: getCheck('is_unemployed_youth'),
		is_pwd: getCheck('is_pwd'),
		disability_type: getVal('disability_type'),
		has_specific_needs: getCheck('has_specific_needs'),
		specific_needs_condition: getVal('specific_needs_condition'),
		is_ip: getCheck('is_ip'),
		tribe_name: getVal('tribe_name'),
		is_muslim: getCheck('is_muslim'),
		muslim_group: getVal('muslim_group'),
		education_level: getVal('education_level'),
		course: getVal('course'),
		school_name: getVal('school_name'),
		is_scholar: getCheck('is_scholar'),
		scholarship_program: getVal('scholarship_program'),
		work_status: getVal('work_status'),
		registered_voter_sk: getCheck('registered_voter_sk'),
		registered_voter_national: getCheck('registered_voter_national'),
		voted_last_sk: getCheck('voted_last_sk'),
		attended_kk_assembly: getCheck('attended_kk_assembly'),
		kk_assembly_times: Math.max(0, kk_times),
		kk_assembly_no_reason: getVal('kk_assembly_no_reason'),
		is_4ps: getCheck('is_4ps'),
		number_of_children: Math.max(0, num_children)
	};

	const existingId = getVal('youth-id');
	if (!existingId && !validateTab('#tab-civic')) {
		showModalAlert('Please complete Civic & Other before saving the profile.');
		return;
	}
	if (existingId) data.id = parseInt(existingId);

	const method = data.id ? 'PUT' : 'POST';
	fetch('/api/youth/', {
		method: method,
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(data)
	}).then(res => {
		return res.text().then(text => {
			try {
				const obj = JSON.parse(text);
				if (res.ok) {
					bootstrap.Modal.getInstance(document.getElementById('youthModal')).hide();
					fetchYouths();
				} else {
					console.error('API error JSON:', obj);
					alert(obj.error || JSON.stringify(obj));
				}
			} catch (err) {
				console.error('Non-JSON response:', text);
				if (res.ok) {
					bootstrap.Modal.getInstance(document.getElementById('youthModal')).hide();
					fetchYouths();
				} else {
					alert(text);
				}
			}
		});
	}).catch(err => {
		console.error('Network/fetch error:', err);
		alert('Network error: ' + err.message);
	});
}

function toggleOSY() {
	const isOsy = document.getElementById('is_osy').checked;
	document.getElementById('osy-section').classList.toggle('d-none', !isOsy);
}

function validatePersonalTab() {
	const container = document.getElementById('tab-personal');
	if (!container) return true;
	const requiredElems = container.querySelectorAll('input[required], select[required], textarea[required]');
	for (const el of requiredElems) {
		if (el.disabled) continue;
		if (!el.checkValidity()) {
			try { el.reportValidity(); } catch (e) {}
			el.focus();
			return false;
		}
	}
	return true;
}

function showModalAlert(msg) {
	const modalBody = document.querySelector('#youthModal .modal-body');
	if (!modalBody) return alert(msg);
	const existing = modalBody.querySelector('.temp-modal-alert');
	if (existing) existing.remove();
	const el = document.createElement('div');
	el.className = 'alert alert-warning temp-modal-alert';
	el.style.marginBottom = '10px';
	el.textContent = msg;
	modalBody.insertBefore(el, modalBody.firstChild);
	setTimeout(() => el.remove(), 3500);
}

function updateTabState() {
	const personalValid = validatePersonalTab();
	const groupsValid = personalValid && isTabValid('#tab-groups');
	const eduValid = personalValid && groupsValid && isTabValid('#tab-edu');
	const civicValid = personalValid && groupsValid && eduValid && isTabValid('#tab-civic');

	const tabLinks = document.querySelectorAll('#formTabsBS a[data-bs-toggle="tab"]');
	tabLinks.forEach(link => {
		const href = link.getAttribute('href');
		if (href === '#tab-personal') {
			link.classList.remove('disabled');
			link.removeAttribute('aria-disabled');
			link.removeAttribute('data-disabled');
			return;
		}
		if (href === '#tab-groups') {
			if (!personalValid) {
				link.classList.add('disabled'); link.setAttribute('aria-disabled','true'); link.setAttribute('data-disabled','true');
			} else { link.classList.remove('disabled'); link.removeAttribute('aria-disabled'); link.removeAttribute('data-disabled'); }
			return;
		}
		if (href === '#tab-edu') {
			if (!groupsValid) { link.classList.add('disabled'); link.setAttribute('aria-disabled','true'); link.setAttribute('data-disabled','true'); }
			else { link.classList.remove('disabled'); link.removeAttribute('aria-disabled'); link.removeAttribute('data-disabled'); }
			return;
		}
		if (href === '#tab-civic') {
			if (!eduValid) { link.classList.add('disabled'); link.setAttribute('aria-disabled','true'); link.setAttribute('data-disabled','true'); }
			else { link.classList.remove('disabled'); link.removeAttribute('aria-disabled'); link.removeAttribute('data-disabled'); }
			return;
		}
		link.classList.remove('disabled'); link.removeAttribute('aria-disabled'); link.removeAttribute('data-disabled');
	});
}

function isTabValid(tabSelector) {
	if (!tabSelector) return true;
	const sel = tabSelector.startsWith('#') ? tabSelector : ('#' + tabSelector.replace(/^#/, ''));
	const container = document.querySelector(sel);
	if (!container) return true;
	const requiredElems = container.querySelectorAll('input[required], select[required], textarea[required]');
	for (const el of requiredElems) {
		if (el.disabled) continue;
		if (el.tagName.toLowerCase() === 'select' && !el.value) {
			if (el.id === 'barangay_id' && currentBarangayId) {
				try { el.value = currentBarangayId; } catch (e) {}
			}
		}
		if (!el.checkValidity()) return false;
	}
	return true;
}

function initFormNavigation() {
	const tabLinks = document.querySelectorAll('#formTabsBS a[data-bs-toggle="tab"]');
	tabLinks.forEach(link => {
		link.addEventListener('show.bs.tab', (e) => {
			const targetHref = link.getAttribute('href');
			if (link.getAttribute('data-disabled') === 'true') {
				e.preventDefault();
				if (targetHref === '#tab-groups') showModalAlert('Please complete Personal information before continuing.');
				else if (targetHref === '#tab-edu') showModalAlert('Please complete Groups/Needs before continuing.');
				else if (targetHref === '#tab-civic') showModalAlert('Please complete Edu & Work before continuing.');
				else showModalAlert('Please complete required fields before continuing.');
				return;
			}

			const leaving = e.relatedTarget;
			if (leaving && leaving.getAttribute) {
				const leaveHref = leaving.getAttribute('href');
				if (leaveHref === '#tab-personal' && !validatePersonalTab()) { e.preventDefault(); showModalAlert('Please complete required Personal fields.'); return; }
				if (leaveHref === '#tab-groups' && !validateTab('#tab-groups')) { e.preventDefault(); showModalAlert('Please complete required Groups/Needs fields.'); return; }
				if (leaveHref === '#tab-edu' && !validateTab('#tab-edu')) { e.preventDefault(); showModalAlert('Please complete required Edu & Work fields.'); return; }
			}
		});
		link.addEventListener('click', (ev) => {
			if (link.getAttribute('data-disabled') === 'true') {
				ev.preventDefault();
				ev.stopPropagation();
				showModalAlert('Please complete Personal information before continuing.');
			}
		});
	});

	const personalInputs = document.querySelectorAll('#tab-personal input, #tab-personal select, #tab-personal textarea');
	personalInputs.forEach(inp => {
		inp.addEventListener('input', updateTabState);
		inp.addEventListener('change', updateTabState);
	});

	const groupsInputs = document.querySelectorAll('#tab-groups input, #tab-groups select, #tab-groups textarea');
	groupsInputs.forEach(inp => { inp.addEventListener('input', updateTabState); inp.addEventListener('change', updateTabState); });
	const eduInputs = document.querySelectorAll('#tab-edu input, #tab-edu select, #tab-edu textarea');
	eduInputs.forEach(inp => { inp.addEventListener('input', updateTabState); inp.addEventListener('change', updateTabState); });
	const civicInputs = document.querySelectorAll('#tab-civic input, #tab-civic select, #tab-civic textarea');
	civicInputs.forEach(inp => { inp.addEventListener('input', updateTabState); inp.addEventListener('change', updateTabState); });

	const youthModal = document.getElementById('youthModal');
	if (youthModal) youthModal.addEventListener('shown.bs.modal', () => updateTabState());

	updateTabState();

	document.querySelectorAll('.btn-next').forEach(btn => {
		if (!btn._navAttached) {
			btn.addEventListener('click', (ev) => {
				const tgt = btn.getAttribute('data-target');
				if (tgt) nextTab(tgt);
			});
			btn._navAttached = true;
		}
	});
	document.querySelectorAll('.btn-prev').forEach(btn => {
		if (!btn._navAttached) {
			btn.addEventListener('click', (ev) => {
				const tgt = btn.getAttribute('data-target');
				if (tgt) prevTab(tgt);
			});
			btn._navAttached = true;
		}
	});
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initFormNavigation); else initFormNavigation();

function validateTab(tabSelector) {
	if (!tabSelector) return true;
	const sel = tabSelector.startsWith('#') ? tabSelector : ('#' + tabSelector.replace(/^#/, ''));
	const container = document.querySelector(sel);
	if (!container) return true;
	const requiredElems = container.querySelectorAll('input[required], select[required], textarea[required]');
	for (const el of requiredElems) {
		if (el.disabled) continue;
		if (el.tagName.toLowerCase() === 'select' && !el.value) {
			if (el.id === 'barangay_id' && currentBarangayId) {
				try { el.value = currentBarangayId; } catch (e) {}
			}
		}

		if (!el.checkValidity()) {
			try {
				console.debug('validateTab failed element:', el.id || el.name || el.tagName, el.checkValidity(), el.validationMessage || 'no message');
			} catch (err) {}
			try { el.reportValidity(); } catch (e) {}
			el.focus();
			return false;
		}
	}

	if (sel === '#tab-groups') {
		return validateGroupsTab();
	}
	if (sel === '#tab-edu') {
		return validateEduTab();
	}
	if (sel === '#tab-civic') {
		return validateCivicTab();
	}
	return true;
}

function validateCivicTab() {
	const attended = !!document.getElementById('attended_kk_assembly') && document.getElementById('attended_kk_assembly').checked;
	const timesEl = document.getElementById('kk_assembly_times');
	const reasonEl = document.getElementById('kk_assembly_no_reason');
	const is4ps = !!document.getElementById('is_4ps') && document.getElementById('is_4ps').checked;
	const numChildrenEl = document.getElementById('number_of_children');

	const reasonVal = reasonEl ? String(reasonEl.value || '').trim() : '';
	if (!attended && reasonVal === '') {
		showModalAlert('Please indicate whether the youth attended KK Assembly or provide a reason in Civic & Other.');
		if (reasonEl) reasonEl.focus();
		return false;
	}

	if (attended) {
		const times = timesEl ? parseInt(timesEl.value || 0) : 0;
		if (!(times > 0)) {
			showModalAlert('Please enter how many times the youth attended KK Assembly (must be > 0).');
			if (timesEl) timesEl.focus();
			return false;
		}
	}

	if (is4ps) {
		const n = numChildrenEl ? parseInt(numChildrenEl.value || 0) : 0;
		if (!(n > 0)) {
			showModalAlert('Please provide number of children for 4Ps beneficiary in Civic & Other.');
			if (numChildrenEl) numChildrenEl.focus();
			return false;
		}
	}

	return true;
}

function validateGroupsTab() {
	const isInSchool = !!document.getElementById('is_in_school') && document.getElementById('is_in_school').checked;
	const isOsy = !!document.getElementById('is_osy') && document.getElementById('is_osy').checked;
	const isWorking = !!document.getElementById('is_working_youth') && document.getElementById('is_working_youth').checked;
	const isUnemployed = !!document.getElementById('is_unemployed_youth') && document.getElementById('is_unemployed_youth').checked;
	const isIp = !!document.getElementById('is_ip') && document.getElementById('is_ip').checked;
	const isPwd = !!document.getElementById('is_pwd') && document.getElementById('is_pwd').checked;

	if (!isInSchool && !isOsy && !isWorking && !isUnemployed && !isIp && !isPwd) {
		showModalAlert('Please select at least one Youth Classification in Groups/Needs.');
		const first = document.getElementById('is_in_school') || document.getElementById('is_osy') || document.getElementById('is_working_youth');
		if (first) first.focus();
		return false;
	}

	if (isOsy) {
		const prog = document.getElementById('osy_program_type') && document.getElementById('osy_program_type').value;
		const reason = document.getElementById('osy_reason_no_enroll') && document.getElementById('osy_reason_no_enroll').value;
		if (!prog && !reason) {
			showModalAlert('OSY selected: consider setting Program or Reason fields in Groups/Needs.');
		}
	}
	return true;
}

function validateEduTab() {
	const edu = document.getElementById('education_level');
	const work = document.getElementById('work_status');
	if (edu && String(edu.value || '').trim() === '') {
		showModalAlert('Please select Highest Education in Edu & Work.');
		try { edu.focus(); } catch (e) {}
		return false;
	}
	if (work && String(work.value || '').trim() === '') {
		showModalAlert('Please provide Work Status in Edu & Work.');
		try { work.focus(); } catch (e) {}
		return false;
	}
	return true;
}

function syncModalTabBtn(targetSelector) {
	const tabId = targetSelector.replace(/^#/, '');
	document.querySelectorAll('.modal-tab-btn').forEach(btn => {
		const onclickVal = btn.getAttribute('onclick') || '';
		btn.classList.toggle('active', onclickVal.includes(tabId));
	});
}

function nextTab(targetSelector) {
	updateTabState();
	const activeLink = document.querySelector('#formTabsBS a.active');
	const leaving = activeLink ? (activeLink.getAttribute('href') || '') : '';
	if (leaving && !validateTab(leaving)) {
		if (leaving === '#tab-personal') showModalAlert('Please complete required Personal fields.');
		else if (leaving === '#tab-groups') showModalAlert('Please complete required Groups/Needs fields.');
		else if (leaving === '#tab-edu') showModalAlert('Please complete required Edu & Work fields.');
		else showModalAlert('Please complete required fields before continuing.');
		return;
	}

	const target = document.querySelector(`#formTabsBS a[href="${targetSelector}"]`);
	if (!target) return console.warn('nextTab: target not found', targetSelector);

	if (target.getAttribute('data-disabled') === 'true') {
		const tgt = target.getAttribute('href');
		if (tgt === '#tab-groups') showModalAlert('Please complete Personal information before continuing.');
		else if (tgt === '#tab-edu') showModalAlert('Please complete Groups/Needs before continuing.');
		else if (tgt === '#tab-civic') showModalAlert('Please complete Edu & Work before continuing.');
		else showModalAlert('Please complete required fields before continuing.');
		return;
	}

	try {
		new bootstrap.Tab(target).show();
		syncModalTabBtn(targetSelector);
		updateTabState();
		return;
	} catch (e) {
		try { target.click(); syncModalTabBtn(targetSelector); updateTabState(); return; } catch (e2) {}
	}

	activateTab(targetSelector);
}

function prevTab(targetSelector) {
	const target = document.querySelector(`#formTabsBS a[href="${targetSelector}"]`);
	if (!target) return console.warn('prevTab: target not found', targetSelector);
	try { new bootstrap.Tab(target).show(); syncModalTabBtn(targetSelector); updateTabState(); return; } catch (e) {
		try { target.click(); syncModalTabBtn(targetSelector); updateTabState(); return; } catch (e2) {}
	}
	activateTab(targetSelector);
}

window.nextTab = nextTab;
window.prevTab = prevTab;

function activateTab(targetSelector) {
	const link = document.querySelector(`#formTabsBS a[href="${targetSelector}"]`);
	const pane = document.querySelector(targetSelector);
	if (!link || !pane) return console.warn('activateTab: missing link or pane', targetSelector, link, pane);

	document.querySelectorAll('#formTabsBS a[data-bs-toggle="tab"]').forEach(a => {
		a.classList.remove('active');
		a.setAttribute('aria-selected', 'false');
	});

	document.querySelectorAll('.tab-pane').forEach(p => {
		p.classList.remove('show');
		p.classList.remove('active');
		p.setAttribute('aria-hidden', 'true');
	});

	link.classList.add('active');
	link.setAttribute('aria-selected', 'true');
	pane.classList.add('show');
	pane.classList.add('active');
	pane.setAttribute('aria-hidden', 'false');

	syncModalTabBtn(targetSelector);
	updateTabState();
}

function openSidebar() {
	const menu = document.getElementById('side-menu');
	const overlay = document.getElementById('side-overlay');
	if (menu) {
		const btn = document.getElementById('menu-toggle');
		if (btn) {
			const rect = btn.getBoundingClientRect();
			const leftPos = Math.max(0, Math.round(rect.left));
			menu.style.left = leftPos + 'px';
		} else {
			menu.style.left = '';
		}
		menu.classList.add('open');
		menu.setAttribute('aria-hidden', 'false');
	}
	if (overlay) {
		overlay.classList.add('show');
		overlay.setAttribute('aria-hidden', 'false');
	}
	document.body.classList.add('side-open');
}

function closeSidebar() {
	const menu = document.getElementById('side-menu');
	const overlay = document.getElementById('side-overlay');
	if (menu) {
		menu.classList.remove('open');
		menu.setAttribute('aria-hidden', 'true');
		menu.style.left = '';
	}
	if (overlay) {
		overlay.classList.remove('show');
		overlay.setAttribute('aria-hidden', 'true');
	}
	document.body.classList.remove('side-open');
}

function toggleSidebar() {
	const menu = document.getElementById('side-menu');
	if (!menu) return;
	if (menu.classList.contains('open')) closeSidebar(); else openSidebar();
}

document.addEventListener('keydown', (e) => {
	if (e.key === 'Escape') {
		const menu = document.getElementById('side-menu');
		if (menu && menu.classList.contains('open')) closeSidebar();
	}
});

let sidebarHoverTimer = null;
const HOVER_OPEN_DELAY = 120; 
const HOVER_CLOSE_DELAY = 300; 
const SUPPORTS_HOVER = (window.matchMedia && window.matchMedia('(hover: hover)').matches) && !('ontouchstart' in window);

function enableSidebarHover() {
	if (!SUPPORTS_HOVER) return;
	const btn = document.getElementById('menu-toggle');
	const menu = document.getElementById('side-menu');
	if (!btn || !menu) return;

	btn.addEventListener('mouseenter', () => {
		if (sidebarHoverTimer) { clearTimeout(sidebarHoverTimer); sidebarHoverTimer = null; }
		sidebarHoverTimer = setTimeout(() => { openSidebar(); sidebarHoverTimer = null; }, HOVER_OPEN_DELAY);
	});

	btn.addEventListener('mouseleave', () => {
		if (sidebarHoverTimer) { clearTimeout(sidebarHoverTimer); sidebarHoverTimer = null; }
		sidebarHoverTimer = setTimeout(() => { closeSidebar(); sidebarHoverTimer = null; }, HOVER_CLOSE_DELAY);
	});

	menu.addEventListener('mouseenter', () => {
		if (sidebarHoverTimer) { clearTimeout(sidebarHoverTimer); sidebarHoverTimer = null; }
	});

	menu.addEventListener('mouseleave', () => {
		if (sidebarHoverTimer) { clearTimeout(sidebarHoverTimer); }
		sidebarHoverTimer = setTimeout(() => { closeSidebar(); sidebarHoverTimer = null; }, HOVER_CLOSE_DELAY);
	});
}

document.addEventListener('DOMContentLoaded', enableSidebarHover);

function deleteYouth(id) {
	const y = getYouthById(id);
	if (!y) return;

	if (confirm(`Are you sure you want to delete the record for ${y.name}?`)) {
		fetch('/api/youth/', {
			method: 'DELETE',
			headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({ id: id })
		}).then(res => {
			if(res.ok) {
				alert('Deleted successfully');
				fetchYouths();
			} else {
				res.json().then(e => alert(e.error));
			}
		});
	}
}

function viewFullSummary(id) {
	const y = getYouthById(id);
	if (!y) return alert("Error: Data not found");

	const d = y.full_data;
	const content = document.getElementById('summary-content');
    
	const fmt = (val) => val ? '<span class="text-success fw-bold">Yes</span>' : '<span class="text-danger">No</span>';

	content.innerHTML = `
		<div class="row mb-3">
			<div class="col-md-6 border-end">
				<h6 class="text-primary border-bottom">Personal Information</h6>
				<p><strong>Name:</strong> ${y.name}</p>
				<p><strong>Sex:</strong> ${y.sex} | <strong>Status:</strong> ${d.civil_status}</p>
				<p><strong>Birthdate:</strong> ${d.birthdate || 'N/A'}</p>
				<p><strong>Religion:</strong> ${d.religion || 'N/A'}</p>
				<p><strong>Contact:</strong> ${d.contact_number || 'N/A'}</p>
			</div>
			<div class="col-md-6">
				<h6 class="text-primary border-bottom">Education & Work</h6>
				<p><strong>Level:</strong> ${y.education_level}</p>
				<p><strong>Course:</strong> ${d.course || 'N/A'}</p>
				<p><strong>School:</strong> ${d.school_name || 'N/A'}</p>
				<p><strong>Work Status:</strong> ${d.work_status || 'N/A'}</p>
				<p><strong>Scholar:</strong> ${fmt(d.is_scholar)} (${d.scholarship_program || 'N/A'})</p>
			</div>
		</div>
		<hr>
		<div class="row">
			<div class="col-md-4 border-end">
				<h6 class="text-primary border-bottom">Classifications</h6>
				<p>In School: ${fmt(d.is_in_school)}</p>
				<p>OSY: ${fmt(d.is_osy)}</p>
				<p>4Ps: ${fmt(d.is_4ps)}</p>
			</div>
			<div class="col-md-4 border-end">
				<h6 class="text-primary border-bottom">Special Needs/Group</h6>
				<p>PWD: ${fmt(d.is_pwd)} (${d.disability_type || 'None'})</p>
				<p>IP/7 Tribes: ${fmt(d.is_ip)} (${d.tribe_name || 'N/A'})</p>
				<p>Muslim: ${fmt(d.is_muslim)} (${d.muslim_group || 'N/A'})</p>
			</div>
			<div class="col-md-4">
				<h6 class="text-primary border-bottom">Civic / Others</h6>
				<p>SK Voter: ${fmt(d.registered_voter_sk)}</p>
				<p>National Voter: ${fmt(d.registered_voter_national)}</p>
				<p>Attended KK: ${fmt(d.attended_kk_assembly)} (${d.kk_assembly_times || 0} times)</p>
			</div>
		</div>
	`;
    
	new bootstrap.Modal(document.getElementById('summaryModal')).show();
}


window.openBarangay = openBarangay;
window.showDashboard = showDashboard;
window.showAdminAccountSection = showAdminAccountSection;
window.showLoginModal = showLoginModal;
window.handleAuth = handleAuth;
window.logout = logout;
window.openModal = openModal;
window.editYouth = editYouth;
window.deleteYouth = deleteYouth;
window.viewFullSummary = viewFullSummary;
window.saveYouth = saveYouth;
window.toggleOSY = toggleOSY;
window.downloadBarangaySummaryCSV = downloadBarangaySummaryCSV;
window.downloadBarangaySummaryPDF = downloadBarangaySummaryPDF;
window.disableBarangayAccount = disableBarangayAccount;
window.enableBarangayAccount = enableBarangayAccount;

