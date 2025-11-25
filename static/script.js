async function loadItems() {
  const res = await fetch('/api/items');
  const data = await res.json();
  const tbody = document.querySelector('#items-table tbody');
  if (tbody) {
    tbody.innerHTML = '';
    data.forEach(i => {
      const tr = document.createElement('tr');
      const editHtml = (window.isAdmin ? `<a href="/items/${i.id}/edit" class="btn">Edit</a>` : '');
      const deleteHtml = (window.isAdmin ? `<button onclick="deleteItem(${i.id})"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3v3H4v2h16V6h-6V3z"></path><path d="M5 9l1 12h12l1-12H5z"></path></svg>Delete</button>` : '');
      const actionHtml = `${editHtml} ${deleteHtml}`;
      tr.innerHTML = `
        <td>${i.id}</td>
        <td>${i.name}</td>
        <td>${i.description || ''}</td>
        <td>${i.quantity}</td>
        <td>${i.reorder_level || 5}</td>
        <td>${i.price || 0}</td>
        <td>${i.supplier_name || ''}</td>
        <td>${actionHtml}</td>
      `;
      tbody.appendChild(tr);
    });
  }
  const spSelect = document.getElementById('item-supplier');
  if (spSelect) {
    spSelect.innerHTML = '<option value="">-- none --</option>';
    const sres = await fetch('/api/suppliers');
    const ss = await sres.json();
    ss.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.supplier_id;
      opt.textContent = s.name;
      spSelect.appendChild(opt);
    });
  }
}

async function addItem() {
  const name = document.getElementById('name')?.value.trim() || '';
  const desc = document.getElementById('desc')?.value.trim() || '';
  const qty = parseInt(document.getElementById('qty')?.value || '0', 10) || 0;
  const reorder = parseInt(document.getElementById('reorder')?.value || '5', 10) || 5;
  const price = parseFloat(document.getElementById('price')?.value || '0') || 0;
  const supplier_id = document.getElementById('item-supplier')?.value || null;
  if (!name) { alert('Name required'); return; }
  await fetch('/api/items', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name, description: desc, quantity: qty, reorder_level: reorder,
      price: price, supplier_id: supplier_id ? parseInt(supplier_id) : null
    })
  });
  ['name','desc','qty','reorder','price'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const sp = document.getElementById('item-supplier'); if (sp) sp.value = '';
  loadItems();
}

async function deleteItem(id) {
  await fetch(`/api/items/${id}`, { method: 'DELETE' });
  loadItems();
}

async function loadStockItems() {
  const res = await fetch('/api/items');
  const items = await res.json();
  const select = document.getElementById('stock-item');
  select.innerHTML = '';
  items.forEach(i => {
    const opt = document.createElement('option');
    opt.value = i.id;
    opt.textContent = `${i.name} (Qty: ${i.quantity})`;
    select.appendChild(opt);
  });
}

async function addStock() {
  const item_id = document.getElementById('stock-item').value;
  const quantity = parseInt(document.getElementById('stock-qty').value);
  const type = document.getElementById('stock-type').value;

  const res = await fetch('/api/stock', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({item_id, quantity, type})
  });

  const data = await res.json();
  if (data.error) alert(data.error);
  else alert("Stock updated!");

  loadStockItems();
  loadStockHistory();
}

async function loadStockHistory() {
  const res = await fetch('/api/stock_history');
  const data = await res.json();
  const tbody = document.querySelector('#stock-history tbody');
  tbody.innerHTML = '';
  data.forEach(t => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${t.name}</td>
      <td>${t.type}</td>
      <td>${t.quantity}</td>
      <td>${t.date}</td>
    `;
    tbody.appendChild(tr);
  });
}

window.onload = function() {
  if (window.location.pathname === '/stock') {
    loadStockItems();
    loadStockHistory();
  } else {
    loadItems?.();
  }
};
async function loadReports() {
  const res = await fetch('/api/reports');
  const data = await res.json();

  // Fill the table
  const tbody = document.querySelector('#report-table tbody');
  tbody.innerHTML = '';
  data.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.name}</td>
      <td>${r.total_in || 0}</td>
      <td>${r.total_out || 0}</td>
    `;
    tbody.appendChild(tr);
  });

  // Draw chart
  const ctx = document.getElementById('reportChart');
  const labels = data.map(r => r.name);
  const inData = data.map(r => r.total_in || 0);
  const outData = data.map(r => r.total_out || 0);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Stock In', data: inData, backgroundColor: 'rgba(40, 167, 69, 0.7)' },
        { label: 'Stock Out', data: outData, backgroundColor: 'rgba(220, 53, 69, 0.7)' }
      ]
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true } }
    }
  });
}

window.onload = function() {
  const path = window.location.pathname;
  if (path === '/stock') {
    loadStockItems();
    loadStockHistory();
  } else if (path === '/items') {
    loadItems();
  } else if (path === '/reports') {
    loadReports();
  } else if (path === '/suppliers') {
    loadSuppliers();
  }
};

try { if (window.feather) { window.feather.replace(); } } catch (e) {}

async function loadSuppliers() {
  const tbody = document.querySelector('#suppliers-table tbody');
  if (!tbody) return;
  const res = await fetch('/api/suppliers');
  const data = await res.json();
  tbody.innerHTML = '';
  data.forEach(s => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${s.supplier_id}</td>
      <td>${s.name}</td>
      <td>${s.contact || ''}</td>
      <td><button onclick="deleteSupplier(${s.supplier_id})"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3v3H4v2h16V6h-6V3z"></path><path d="M5 9l1 12h12l1-12H5z"></path></svg>Delete</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function addSupplier() {
  const name = document.getElementById('supplier-name')?.value.trim() || '';
  const contact = document.getElementById('supplier-contact')?.value.trim() || '';
  if (!name) { alert('Supplier name required'); return; }
  await fetch('/api/suppliers', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, contact})
  });
  const n = document.getElementById('supplier-name'); if (n) n.value = '';
  const c = document.getElementById('supplier-contact'); if (c) c.value = '';
  loadSuppliers();
}

async function deleteSupplier(id) {
  if (!confirm('Delete supplier?')) return;
  await fetch(`/api/suppliers/${id}`, { method: 'DELETE' });
  loadSuppliers();
}
