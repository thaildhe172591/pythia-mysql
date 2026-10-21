-- Purpose: whether views still resolve: MariaDB opens each one and says why
--          it cannot, the cause first (a missing table or column), then the
--          view's own error. It reads only, and runs in a READ ONLY session
-- Binds:   none: /*VIEWS*/ is a list of `schema`.`view` names pythia quoted
-- Returns: TABLE, OP, MSG_TYPE, MSG_TEXT
check table /*VIEWS*/
