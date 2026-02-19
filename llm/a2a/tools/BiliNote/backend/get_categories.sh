#!/bin/bash
docker exec wordpress_db mysql -uwordpressuser -pwordpresspassword wordpress -e "SELECT term_id, name, slug FROM wp_terms WHERE term_id IN (SELECT term_id FROM wp_term_taxonomy WHERE taxonomy='category');"
