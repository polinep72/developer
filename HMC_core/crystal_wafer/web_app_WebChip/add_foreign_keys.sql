-- SQL скрипт для добавления внешних ключей (foreign keys) 
-- в таблицы invoice_p, consumption_p, invoice_f, consumption_f
-- по аналогии с таблицами invoice и consumption

-- ВАЖНО: Перед выполнением убедитесь, что все данные в таблицах корректны
-- и соответствуют справочникам. Для полей, которые могут быть NULL, 
-- внешние ключи не создаются или создаются с условием NOT NULL.

-- Внешние ключи для таблицы invoice_p
ALTER TABLE invoice_p
    ADD CONSTRAINT fk_invoice_p_id_start FOREIGN KEY (id_start) REFERENCES start_p(id),
    ADD CONSTRAINT fk_invoice_p_id_pr FOREIGN KEY (id_pr) REFERENCES pr(id),
    ADD CONSTRAINT fk_invoice_p_id_tech FOREIGN KEY (id_tech) REFERENCES tech(id),
    ADD CONSTRAINT fk_invoice_p_id_lot FOREIGN KEY (id_lot) REFERENCES lot(id),
    ADD CONSTRAINT fk_invoice_p_id_wafer FOREIGN KEY (id_wafer) REFERENCES wafer(id),
    ADD CONSTRAINT fk_invoice_p_id_quad FOREIGN KEY (id_quad) REFERENCES quad(id),
    ADD CONSTRAINT fk_invoice_p_id_in_lot FOREIGN KEY (id_in_lot) REFERENCES in_lot(id),
    ADD CONSTRAINT fk_invoice_p_id_chip FOREIGN KEY (id_chip) REFERENCES chip(id),
    ADD CONSTRAINT fk_invoice_p_id_n_chip FOREIGN KEY (id_n_chip) REFERENCES n_chip(id),
    ADD CONSTRAINT fk_invoice_p_id_pack FOREIGN KEY (id_pack) REFERENCES pack(id),
    ADD CONSTRAINT fk_invoice_p_id_stor FOREIGN KEY (id_stor) REFERENCES stor(id),
    ADD CONSTRAINT fk_invoice_p_id_cells FOREIGN KEY (id_cells) REFERENCES cells(id),
    ADD CONSTRAINT fk_invoice_p_user_entry FOREIGN KEY (user_entry_id) REFERENCES public.users(id);

-- Внешний ключ для id_size (может быть NULL, поэтому создаем отдельно, если поле NOT NULL)
-- ALTER TABLE invoice_p ADD CONSTRAINT fk_invoice_p_id_size FOREIGN KEY (id_size) REFERENCES size_c(id);

-- Внешние ключи для таблицы consumption_p
ALTER TABLE consumption_p
    ADD CONSTRAINT fk_consumption_p_id_start FOREIGN KEY (id_start) REFERENCES start_p(id),
    ADD CONSTRAINT fk_consumption_p_id_pr FOREIGN KEY (id_pr) REFERENCES pr(id),
    ADD CONSTRAINT fk_consumption_p_id_tech FOREIGN KEY (id_tech) REFERENCES tech(id),
    ADD CONSTRAINT fk_consumption_p_id_lot FOREIGN KEY (id_lot) REFERENCES lot(id),
    ADD CONSTRAINT fk_consumption_p_id_wafer FOREIGN KEY (id_wafer) REFERENCES wafer(id),
    ADD CONSTRAINT fk_consumption_p_id_quad FOREIGN KEY (id_quad) REFERENCES quad(id),
    ADD CONSTRAINT fk_consumption_p_id_in_lot FOREIGN KEY (id_in_lot) REFERENCES in_lot(id),
    ADD CONSTRAINT fk_consumption_p_id_chip FOREIGN KEY (id_chip) REFERENCES chip(id),
    ADD CONSTRAINT fk_consumption_p_id_n_chip FOREIGN KEY (id_n_chip) REFERENCES n_chip(id),
    ADD CONSTRAINT fk_consumption_p_id_pack FOREIGN KEY (id_pack) REFERENCES pack(id),
    ADD CONSTRAINT fk_consumption_p_id_stor FOREIGN KEY (id_stor) REFERENCES stor(id),
    ADD CONSTRAINT fk_consumption_p_id_cells FOREIGN KEY (id_cells) REFERENCES cells(id),
    ADD CONSTRAINT fk_consumption_p_user_entry FOREIGN KEY (user_entry_id) REFERENCES public.users(id);

-- Внешние ключи для таблицы invoice_f
ALTER TABLE invoice_f
    ADD CONSTRAINT fk_invoice_f_id_start FOREIGN KEY (id_start) REFERENCES start_p(id),
    ADD CONSTRAINT fk_invoice_f_id_pr FOREIGN KEY (id_pr) REFERENCES pr(id),
    ADD CONSTRAINT fk_invoice_f_id_tech FOREIGN KEY (id_tech) REFERENCES tech(id),
    ADD CONSTRAINT fk_invoice_f_id_lot FOREIGN KEY (id_lot) REFERENCES lot(id),
    ADD CONSTRAINT fk_invoice_f_id_wafer FOREIGN KEY (id_wafer) REFERENCES wafer(id),
    ADD CONSTRAINT fk_invoice_f_id_quad FOREIGN KEY (id_quad) REFERENCES quad(id),
    ADD CONSTRAINT fk_invoice_f_id_in_lot FOREIGN KEY (id_in_lot) REFERENCES in_lot(id),
    ADD CONSTRAINT fk_invoice_f_id_chip FOREIGN KEY (id_chip) REFERENCES chip(id),
    ADD CONSTRAINT fk_invoice_f_id_n_chip FOREIGN KEY (id_n_chip) REFERENCES n_chip(id),
    ADD CONSTRAINT fk_invoice_f_id_pack FOREIGN KEY (id_pack) REFERENCES pack(id),
    ADD CONSTRAINT fk_invoice_f_id_stor FOREIGN KEY (id_stor) REFERENCES stor(id),
    ADD CONSTRAINT fk_invoice_f_id_cells FOREIGN KEY (id_cells) REFERENCES cells(id),
    ADD CONSTRAINT fk_invoice_f_user_entry FOREIGN KEY (user_entry_id) REFERENCES public.users(id);

-- Внешний ключ для id_size (может быть NULL, поэтому создаем отдельно, если поле NOT NULL)
-- ALTER TABLE invoice_f ADD CONSTRAINT fk_invoice_f_id_size FOREIGN KEY (id_size) REFERENCES size_c(id);

-- Внешние ключи для таблицы consumption_f
ALTER TABLE consumption_f
    ADD CONSTRAINT fk_consumption_f_id_start FOREIGN KEY (id_start) REFERENCES start_p(id),
    ADD CONSTRAINT fk_consumption_f_id_pr FOREIGN KEY (id_pr) REFERENCES pr(id),
    ADD CONSTRAINT fk_consumption_f_id_tech FOREIGN KEY (id_tech) REFERENCES tech(id),
    ADD CONSTRAINT fk_consumption_f_id_lot FOREIGN KEY (id_lot) REFERENCES lot(id),
    ADD CONSTRAINT fk_consumption_f_id_wafer FOREIGN KEY (id_wafer) REFERENCES wafer(id),
    ADD CONSTRAINT fk_consumption_f_id_quad FOREIGN KEY (id_quad) REFERENCES quad(id),
    ADD CONSTRAINT fk_consumption_f_id_in_lot FOREIGN KEY (id_in_lot) REFERENCES in_lot(id),
    ADD CONSTRAINT fk_consumption_f_id_chip FOREIGN KEY (id_chip) REFERENCES chip(id),
    ADD CONSTRAINT fk_consumption_f_id_n_chip FOREIGN KEY (id_n_chip) REFERENCES n_chip(id),
    ADD CONSTRAINT fk_consumption_f_id_pack FOREIGN KEY (id_pack) REFERENCES pack(id),
    ADD CONSTRAINT fk_consumption_f_id_stor FOREIGN KEY (id_stor) REFERENCES stor(id),
    ADD CONSTRAINT fk_consumption_f_id_cells FOREIGN KEY (id_cells) REFERENCES cells(id),
    ADD CONSTRAINT fk_consumption_f_user_entry FOREIGN KEY (user_entry_id) REFERENCES public.users(id);

