-- The live check's fixture for MariaDB: app_owner.sql's objects as MariaDB
-- spells them (an IGNORED index, a collation 10.11 has), and what only
-- MariaDB keeps: a column-level CHECK, a sequence and, in sql_mode=ORACLE, a
-- package. It drops and recreates two databases: load it into a disposable
-- server only, never a shared one.
drop database if exists app_owner;
drop database if exists reporting;
create database app_owner default character set utf8mb4 collate utf8mb4_unicode_ci;
create database reporting default character set utf8mb4 collate utf8mb4_unicode_ci;

create table app_owner.t_order (
    id bigint unsigned not null auto_increment,
    status varchar(10) not null default 'DRAFT' comment 'DRAFT until paid',
    total decimal(12,2) not null default 0,
    note varchar(40) character set latin1 collate latin1_bin null,
    created timestamp(3) not null default current_timestamp(3) on update current_timestamp(3),
    token char(36) not null default (uuid()),
    twice decimal(13,2) generated always as (total * 2) virtual,
    primary key (id),
    unique key uk_order_token (token),
    key ix_order_status (status, total desc),
    key ix_order_note (note(8)) ignored comment 'by note',
    constraint ck_order_status check (status in ('DRAFT', 'PAID'))
) engine=InnoDB comment='Customer orders, ''all'' of them';

create table app_owner.t_order_line (
    id int not null auto_increment primary key,
    order_id bigint unsigned not null,
    qty int not null check (qty > 0),
    amount int generated always as (qty * 2) stored,
    constraint fk_line_order foreign key (order_id) references app_owner.t_order (id)
        on delete cascade
);

create table app_owner.t_order_audit (
    id int not null auto_increment primary key,
    order_id bigint unsigned not null,
    at timestamp(3) not null default current_timestamp(3)
);

create view app_owner.v_order_summary as
select status, count(*) as n, sum(total) as total
  from app_owner.t_order
 group by status;

create view reporting.v_paid as
select id, total from app_owner.t_order where status = 'PAID';

DELIMITER //
create function app_owner.f_order_total(p_id bigint unsigned) returns decimal(12,2)
    reads sql data
begin
    -- the total of one order
    return (select total from app_owner.t_order where id = p_id);
end//

create procedure app_owner.p_order_paid(in p_id bigint unsigned, out p_n int)
    modifies sql data
    sql security invoker
    comment 'marks one order paid'
begin
    update app_owner.t_order set status = 'PAID' where id = p_id;
    select count(*) into p_n from app_owner.t_order where status = 'PAID';
end//

create procedure app_owner.p_order_count()
begin
    set @s = 'select count(*) from app_owner.t_order';
    prepare st from @s;
    execute st;
    deallocate prepare st;
end//

create trigger app_owner.trg_order_audit after update on app_owner.t_order for each row
begin
    insert into app_owner.t_order_audit (order_id) values (new.id);
end//

create procedure app_owner.p_broken()
begin
    select missing_col from app_owner.t_missing;
end//

create procedure app_owner.p_order_number(out p_n bigint)
begin
    set p_n = next value for app_owner.s_order;
end//
DELIMITER ;

create sequence app_owner.s_order start with 100 increment by 5 cache 10 comment 'order numbers';

set session sql_mode = 'ORACLE';
DELIMITER //
create package app_owner.pkg_order as
    function f_count return int;
end//
create package body app_owner.pkg_order as
    function f_count return int as
    begin
        return (select count(*) from app_owner.t_order);
    end;
end//
DELIMITER ;
set session sql_mode = default;

create view app_owner.v_total as
select id, app_owner.f_order_total(id) as total from app_owner.t_order;

create event app_owner.ev_purge_audit
    on schedule every 1 day starts '2030-01-01 00:00:00'
    on completion preserve disable comment 'keeps 30 days'
    do delete from app_owner.t_order_audit where at < now() - interval 30 day;

create table app_owner.t_note (id int primary key, body varchar(100));
create view app_owner.v_note as select id, body from app_owner.t_note;
-- v_note is broken from here on: errors must find it
drop table app_owner.t_note;

insert into app_owner.t_order (status, total) values ('DRAFT', 10), ('DRAFT', 20), ('PAID', 30);
