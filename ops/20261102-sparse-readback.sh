sudo -u postgres psql -d vectordb -tAc "SELECT answer_id || ' ||| ' || sparse_embedding::text FROM user_insight.answer WHERE answer_id='A-R001-Q001'" 2>&1
