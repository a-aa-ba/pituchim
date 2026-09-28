FROM php:8.2-apache

# העתקת קבצי הפרויקט לשרת
COPY . /var/www/html/

# מתן הרשאות לשרת Apache לקרוא ולכתוב קבצים (עבור קבצי counter)
RUN chown -R www-data:www-data /var/www/html \
    && chmod -R 755 /var/www/html

EXPOSE 80
