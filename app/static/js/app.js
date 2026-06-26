function updateCountdowns(){
  document.querySelectorAll('.countdown').forEach(el=>{
    const end = new Date(el.dataset.end);
    const diff = end - new Date();
    if(isNaN(end)) return;
    if(diff<=0){ el.textContent='SCADUTO'; el.classList.add('expired'); return; }
    const m=Math.floor(diff/60000), s=Math.floor((diff%60000)/1000);
    el.textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  });
}
setInterval(updateCountdowns,1000); updateCountdowns();

// Versione 29 - apre/chiude il dettaglio prenotazione cliccando su draft/stato
(function(){
  document.querySelectorAll('[data-toggle-detail]').forEach(btn=>{
    btn.addEventListener('click', function(){
      const id = this.getAttribute('data-toggle-detail');
      const row = document.getElementById(id);
      if(!row) return;
      row.classList.toggle('open');
      if(row.classList.contains('open')){
        row.scrollIntoView({behavior:'smooth', block:'nearest'});
      }
    });
  });
})();

// Versione 30 - prenotazione mobile con slot automatici: 40 min per giochi da 30, 70 min per giochi da 60, massimo 6 posti
(function(){
  const root = document.querySelector('[data-public-booking]');
  if(!root) return;

  const games = JSON.parse(root.dataset.games || '[]');
  const bookings = JSON.parse(root.dataset.bookings || '[]');
  const uploadBase = root.dataset.uploadBase || '/static/uploads/';
  const capacity = parseInt(root.dataset.capacity || '6', 10);
  const openTime = root.dataset.open || '10:00';
  const closeTime = root.dataset.close || '23:00';

  const dateInput = document.getElementById('mbDate');
  const gameSelect = document.getElementById('mbGame');
  const slotSelect = document.getElementById('mbSlot');
  const playersBox = document.getElementById('mbPlayers');
  const lobbyList = document.getElementById('mbLobbyList');
  const availabilityText = document.getElementById('mbAvailabilityText');
  const summary = document.getElementById('mbSummary');
  const promoBtn = document.getElementById('mbApplyPromo');

  const hDate = document.getElementById('mbBookingDate');
  const hStart = document.getElementById('mbStartTime');
  const hEnd = document.getElementById('mbEndTime');
  const hService = document.getElementById('mbService');
  const hPeople = document.getElementById('mbPeople');
  const hDuration = document.getElementById('mbDuration');
  const hTotal = document.getElementById('mbTotal');
  const hNotes = document.getElementById('mbNotes');

  const titleEl = document.getElementById('mbGameTitle');
  const descEl = document.getElementById('mbGameDesc');
  const durEl = document.getElementById('mbGameDuration');
  const priceEl = document.getElementById('mbGamePrice');
  const coverEl = document.getElementById('mbGameCover');

  let selectedPeople = 1;
  let currentAvailability = capacity;
  let promoApplied = false;

  function pad(n){ return String(n).padStart(2,'0'); }
  function toMinutes(t){
    const parts = String(t || '00:00').split(':').map(Number);
    return (parts[0] || 0) * 60 + (parts[1] || 0);
  }
  function fmt(min){
    min = ((min % 1440) + 1440) % 1440;
    return pad(Math.floor(min/60)) + ':' + pad(min % 60);
  }
  function money(v){
    return '€' + Number(v || 0).toFixed(2).replace('.', ',');
  }
  function selectedGame(){
    return games.find(g => g.title === gameSelect.value) || games[0] || {title:'',duration:30,price:0,description:'',cover:''};
  }
  function gameDuration(g){
    const d = parseInt(g.duration || 30, 10);
    return d >= 60 ? 60 : 30;
  }
  function slotStep(duration){
    return duration >= 60 ? 70 : 40;
  }
  function overlaps(aStart, aEnd, bStart, bEnd){
    return aStart < bEnd && aEnd > bStart;
  }
  function usedForSlot(start, end){
    const day = dateInput.value;
    if(!day) return 0;
    return bookings
      .filter(b => b.booking_date === day && b.status !== 'cancelled')
      .filter(b => overlaps(start, end, toMinutes(b.start_time), toMinutes(b.end_time || b.start_time)))
      .reduce((sum, b) => sum + parseInt(b.people || 1, 10), 0);
  }
  function buildSlots(){
    const g = selectedGame();
    const duration = gameDuration(g);
    const step = slotStep(duration);
    const startLimit = toMinutes(openTime);
    const endLimit = toMinutes(closeTime);
    const previous = slotSelect.value;
    slotSelect.innerHTML = '';
    for(let t=startLimit; t+duration<=endLimit; t+=step){
      const end = t + duration;
      const used = usedForSlot(t, end);
      const available = Math.max(0, capacity - used);
      const opt = document.createElement('option');
      opt.value = fmt(t);
      opt.dataset.end = fmt(end);
      opt.dataset.available = String(available);
      opt.disabled = available <= 0;
      opt.textContent = fmt(t) + ' - ' + available + ' posti';
      slotSelect.appendChild(opt);
    }
    const same = Array.from(slotSelect.options).find(o => o.value === previous && !o.disabled);
    const firstFree = Array.from(slotSelect.options).find(o => !o.disabled);
    if(same) slotSelect.value = same.value;
    else if(firstFree) slotSelect.value = firstFree.value;
    updateAll();
  }
  function renderPlayers(){
    playersBox.innerHTML = '';
    for(let i=1; i<=capacity; i++){
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'player-btn' + (i === selectedPeople ? ' active' : '');
      btn.textContent = i;
      btn.setAttribute('aria-label', i + ' giocatori');
      if(i > currentAvailability){
        btn.disabled = true;
        btn.classList.add('disabled');
      }
      btn.addEventListener('click', () => {
        selectedPeople = i;
        updateAll();
      });
      playersBox.appendChild(btn);
    }
  }
  function renderGameCard(){
    const g = selectedGame();
    const duration = gameDuration(g);
    titleEl.textContent = g.title || 'Gioco';
    descEl.textContent = g.description || 'Esperienza multiplayer in arena VR.';
    durEl.textContent = duration + ' min';
    priceEl.textContent = money(g.price || 0) + ' / persona';
    if(g.cover){
      coverEl.innerHTML = '<img src="' + uploadBase + g.cover + '" alt="' + g.title.replace(/"/g,'&quot;') + '">';
    }else{
      coverEl.textContent = '🎮';
    }
  }
  function renderLobbies(){
    const day = dateInput.value;
    const g = selectedGame();
    const rows = bookings.filter(b => b.booking_date === day && b.status !== 'cancelled');
    if(!rows.length){
      lobbyList.innerHTML = '<p class="no-lobby">Nessuna lobby pubblica attiva per questo giorno.</p>';
      return;
    }
    lobbyList.innerHTML = rows.slice(0,8).map(b => {
      const used = parseInt(b.people || 1, 10);
      const free = Math.max(0, capacity - used);
      return '<button type="button" class="lobby-item" data-lobby-start="'+b.start_time+'" data-lobby-service="'+String(b.service).replace(/"/g,'&quot;')+'">' +
        '<b>'+b.start_time+' · '+b.service+'</b>' +
        '<span>'+used+'/'+capacity+' posti occupati · '+free+' liberi</span>' +
      '</button>';
    }).join('');
    lobbyList.querySelectorAll('.lobby-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const service = btn.dataset.lobbyService;
        const start = btn.dataset.lobbyStart;
        if(service){ gameSelect.value = service; }
        buildSlots();
        if(start && Array.from(slotSelect.options).some(o => o.value === start && !o.disabled)){
          slotSelect.value = start;
        }
        const radio = document.querySelector('input[name="booking_mode"][value="Unisciti alla lobby"]');
        if(radio) radio.checked = true;
        updateAll();
        slotSelect.scrollIntoView({behavior:'smooth', block:'center'});
      });
    });
  }
  function updateHiddenAndSummary(){
    const g = selectedGame();
    const duration = gameDuration(g);
    const slot = slotSelect.options[slotSelect.selectedIndex];
    const start = slot ? slot.value : '';
    const end = slot ? (slot.dataset.end || fmt(toMinutes(start)+duration)) : '';
    const unit = Number(g.price || 0);
    const subtotal = selectedPeople * unit;
    const total = promoApplied ? Math.max(0, subtotal * 0.90) : subtotal;
    const modeInput = document.querySelector('input[name="booking_mode"]:checked');
    const mode = modeInput ? modeInput.value : 'Nuova partita';

    hDate.value = dateInput.value || '';
    hStart.value = start;
    hEnd.value = end;
    hService.value = g.title || '';
    hPeople.value = String(selectedPeople);
    hDuration.value = String(duration);
    hTotal.value = total.toFixed(2);
    hNotes.value = mode + (promoApplied ? ' | Promo applicata dal modulo pubblico' : '');

    summary.innerHTML = [
      '📅 ' + (dateInput.value || '-'),
      '🎮 ' + (g.title || '-'),
      '🕒 ' + (start || '-') + (end ? '-' + end : ''),
      '👥 ' + selectedPeople,
      '🕹️ ' + mode,
      '💶 ' + money(total) + ' (= ' + money(unit) + '/persona)'
    ].map(x => '<div>'+x+'</div>').join('');
  }
  function updateAvailability(){
    const slot = slotSelect.options[slotSelect.selectedIndex];
    currentAvailability = slot ? parseInt(slot.dataset.available || capacity, 10) : capacity;
    if(selectedPeople > currentAvailability) selectedPeople = Math.max(1, currentAvailability);
    availabilityText.textContent = currentAvailability > 0
      ? 'Posti disponibili in questo orario: ' + currentAvailability + ' su ' + capacity + '.'
      : 'Questo orario è completo. Scegli un altro slot.';
  }
  function updateAll(){
    renderGameCard();
    updateAvailability();
    renderPlayers();
    renderLobbies();
    updateHiddenAndSummary();
  }
  function init(){
    if(dateInput && !dateInput.value){
      const now = new Date();
      dateInput.value = now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate());
    }
    buildSlots();
    dateInput.addEventListener('change', buildSlots);
    gameSelect.addEventListener('change', buildSlots);
    slotSelect.addEventListener('change', updateAll);
    document.querySelectorAll('input[name="booking_mode"]').forEach(r => r.addEventListener('change', updateAll));
    if(promoBtn){
      promoBtn.addEventListener('click', () => {
        promoApplied = !!document.getElementById('mbPromo').value.trim();
        promoBtn.textContent = promoApplied ? 'Applicato' : 'Applica';
        updateAll();
      });
    }
    const form = document.getElementById('mobileBookingForm');
    form.addEventListener('submit', (e) => {
      updateHiddenAndSummary();
      if(!hStart.value || currentAvailability <= 0){
        e.preventDefault();
        alert('Scegli uno slot disponibile.');
      }
    });
  }
  init();
})();
