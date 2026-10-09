/* Integer cents keep previews exact; the server independently uses Decimal. */
(function () {
    function cents(value) {
        const match = /^(?:(\d+)(?:\.(\d{0,2}))?|\.(\d{1,2}))$/.exec(value.trim());
        if (!match) return null;
        const amount = BigInt(match[1] || '0') * 100n + BigInt((match[2] || match[3] || '').padEnd(2, '0'));
        return amount <= 999999999999n ? amount : null;
    }
    function money(value) {
        const sign = value < 0n ? '-' : '';
        const absolute = value < 0n ? -value : value;
        const dollars = (absolute / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return sign + '$' + dollars + '.' + (absolute % 100n).toString().padStart(2, '0');
    }
    function calculate() {
        const values = ['register_cash', 'card_charges', 'daily_card_tips', 'daily_employee_pay', 'starting_cash']
            .map(name => cents(document.getElementById('id_' + name).value));
        const valid = values.every(value => value !== null);
        let subtotal, totalDeposit, cashDeposit;
        if (valid) {
            const [cash, charges, tips, pay, starting] = values;
            subtotal = cash + charges;
            totalDeposit = subtotal + tips;
            cashDeposit = totalDeposit - pay - starting - charges;
        }
        ['subtotal', 'total-deposit', 'cash-deposit'].forEach((id, index) => {
            document.getElementById(id).textContent = valid ? money([subtotal, totalDeposit, cashDeposit][index]) : '—';
        });
        document.getElementById('deposit-warning').hidden = !valid || cashDeposit >= 0n;
    }
    const form = document.getElementById('financial-entry');
    if (form && document.getElementById('subtotal')) {
        form.addEventListener('input', calculate);
        calculate();
    }
})();
