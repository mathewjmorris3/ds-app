/* Integer cents keep previews exact; server calculations use Decimal. */
(function () {
    function cents(value) {
        const match = /^(?:(\d+)(?:\.(\d{0,2}))?|\.(\d{1,2}))$/.exec(value.trim());
        if (!match) return null;
        const amount = BigInt(match[1] || '0') * 100n + BigInt((match[2] || match[3] || '').padEnd(2, '0'));
        return amount <= 999999999999n ? amount : null;
    }
    function money(value) {
        const absolute = value < 0n ? -value : value;
        return (value < 0n ? '-' : '') + '$' + (absolute / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + (absolute % 100n).toString().padStart(2, '0');
    }
    const form = document.getElementById('financial-entry');
    if (!form || !document.getElementById('summary-gross_total')) return;
    const reserve = cents(form.dataset.cashReserve);
    function calculate() {
        const values = {};
        ['register_cash', 'card_charges', 'daily_employee_pay', 'daily_card_tips', 'daily_cash_tips', 'extras'].forEach(name => {
            values[name] = cents(document.getElementById('id_' + name).value);
        });
        values.gross_total = values.register_cash !== null && values.card_charges !== null ? values.register_cash + values.card_charges : null;
        values.cash_deposit = [values.register_cash, values.daily_employee_pay, reserve].every(v => v !== null) ? values.register_cash - values.daily_employee_pay - reserve : null;
        values.credit_card_deposit = values.card_charges;
        Object.entries(values).forEach(([name, value]) => {
            const output = document.getElementById('summary-' + name);
            if (output) output.textContent = value === null ? '—' : money(value);
        });
    }
    form.addEventListener('input', calculate);
    form.addEventListener('change', calculate);
    form.addEventListener('focusout', event => {
        if (event.target.type === 'number') {
            const value = cents(event.target.value);
            if (value !== null) event.target.value = (value / 100n).toString() + '.' + (value % 100n).toString().padStart(2, '0');
        }
    });
    calculate();
})();
