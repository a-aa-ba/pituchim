FROM php:8.2-apache

# העתקת כל קבצי הפרויקט לתיקיית ברירת המחדל של שרת Apache
COPY . /var/www/html/

# יצירת תיקיית האחסון במידה ואינה קיימת, והענקת הרשאות כתיבה למשתמש של השרת (www-data)
RUN mkdir -p /var/www/html/storage && chown -R www-data:www-data /var/www/html/storage

# חשיפת פורט 80 (הפורט ש-Render מאזין לו כברירת מחדל)
EXPOSE 80
