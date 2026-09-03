const {expect} = require('@playwright/test');

// Called by the example smoke suite with its own isolated showcase process.
module.exports = async function exerciseShowcase(page) {
    const section = async title => {
        const tab = page.locator('#showcase-tabs > .tab-bar > .tab-item').filter({hasText: title});
        await tab.click();
        await expect(tab).toHaveClass(/active/);
    };
    await expect(page.locator('#showcase-tabs > .tab-bar > .tab-item')).toHaveCount(6);
    await page.locator('#demo-name').fill('café 日本語 😀');
    await expect(page.locator('#demo-echo')).toHaveText('café 日本語 😀');
    await expect(page.locator('#demo-name')).toBeFocused();
    await expect(page.locator('#demo-password')).toHaveAttribute('type', 'password');
    await page.locator('#demo-lock input').check();
    await expect(page.locator('#demo-name')).toBeDisabled();
    await page.locator('#demo-lock input').uncheck();
    await expect(page.locator('#demo-name')).toBeEnabled();
    await page.locator('#demo-language').selectOption('2');
    await expect(page.locator('#event-log')).toHaveValue(/Language: 日本語/);
    await page.locator('#demo-radio-1 input').check();
    await expect(page.locator('#demo-radio-0 input')).not.toBeChecked();
    await page.locator('#demo-spin input').fill('72');
    await page.locator('#demo-spin input').dispatchEvent('change');
    await expect(page.locator('#demo-slider input')).toHaveValue('72');
    await page.locator('#demo-decimal .spin-btn').last().click();
    await expect(page.locator('#demo-decimal input')).toHaveValue('1.5');

    await section('Data views');
    await page.locator('#demo-filter').fill('Widgets');
    await expect(page.locator('#data-status')).toHaveText('8 / 24 records');
    const cell = page.locator('#demo-table tbody tr').first().locator('td').first();
    await cell.click();
    await expect(cell).toHaveClass(/selected/);
    await cell.fill('Browser edit');
    await page.locator('#demo-filter').focus();
    await expect(page.locator('#event-log')).toHaveValue(/Edited row 1, column 1/);
    await page.locator('#collapse-tree').click();
    await page.locator('#expand-tree').click();

    await section('Layouts');
    const pages = page.locator('#dynamic-tabs > .tab-content > .tab-page');
    await page.locator('#add-tab').click();
    await expect(pages).toHaveCount(2);
    await page.locator('#remove-tab').click();
    await expect(pages).toHaveCount(1);
    await page.locator('#next-page').click();
    await expect(page.locator('#demo-stack > .stacked-page.active')).toHaveText('Stacked page 2');

    await section('Runtime');
    await page.locator('#increment-counter').click();
    await expect(page.locator('#demo-counter')).toHaveText('Counter: 1');
    await page.locator('#block-counter').click();
    await expect(page.locator('#demo-counter')).toHaveText('Counter: 2 (signal blocked)');
    await page.locator('#burst').click();
    await expect(page.locator('#burst-status')).toHaveText('Burst value: 1000 / 1000');
    await page.locator('#add-card').click();
    await expect(page.locator('#card-1')).toBeVisible();
    await page.locator('#delete-card').click();
    await page.locator('#full-refresh').click();
    await expect(page.locator('#card-1')).toHaveCount(0);
    await page.locator('#open-dialog').click();
    await expect(page.locator('#demo-dialog')).toBeVisible();
    await page.locator('#accept-dialog').click();
    await expect(page.locator('#demo-dialog')).not.toBeVisible();
    await page.locator('#start-timer').click();
    await expect(page.locator('#timer-status')).toHaveText(/Timer running · ticks: [1-9]/);
    await page.locator('#stop-timer').click();
    await expect(page.locator('#timer-status')).toHaveText(/Timer stopped/);
    await page.locator('#single-shot').click();
    await expect(page.locator('#event-log')).toHaveValue(/Single-shot timer fired/);

    await section('Painting & styles');
    await expect(page.locator('#paint-gallery canvas')).toBeVisible();
    await expect(page.locator('#paint-gallery canvas')).toHaveAttribute('width', '640');
    await page.locator('#rich-sample').click();
    await expect(page.locator('#demo-rich b')).toHaveText('Safe bold');
    await expect(page.locator('#demo-rich script')).toHaveCount(0);
    await expect(page.locator('#demo-rich a')).not.toHaveAttribute('href', /.+/);
    await expect(page.locator('#demo-rich a')).not.toHaveAttribute('onclick', /.+/);
    await page.locator('#blocked-style').click();
    await expect(page.locator('#event-log')).toHaveValue(/Resource stylesheet rejected: True/);
    await page.locator('#clear-style').click();
    await expect(page.locator('#pysideweb-app-qss')).toHaveCount(0);
    await page.locator('#apply-style').click();
    await expect(page.locator('#pysideweb-app-qss')).toHaveCount(1);

    await section('Compatibility');
    await expect(page.locator('#unsupported-view')).toHaveClass(/widget-unsupported/);
    await page.locator('#inspect-object').click();
    await expect(page.locator('#event-log')).toHaveValue(/QObject findChild: True; parent matches: True/);
    await page.locator('#trigger-action').click();
    await expect(page.locator('#event-log')).toHaveValue(/QAction.triggered received/);
    await page.reload();
    await expect(page.locator('#connection-status .status-text')).toHaveText('Connected');
    await section('Runtime');
    await expect(page.locator('#demo-counter')).toHaveText('Counter: 2 (signal blocked)');
    await expect(page.locator('#card-1')).toHaveCount(0);
};
